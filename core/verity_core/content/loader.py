"""Reads `content/` into nodes and edges.

Records are built with the graph's own models, so their validators apply (a `no_relationship`
mapping with a strength, or an automatable organisational control, fails here). Nothing is
written anywhere: `seed.py` does that, through `GraphRepository`.

Layout under the root; every file is optional:

    frameworks/*.yaml  controls.yaml  mappings/*.yaml  org/*.yaml  decisions/*.yaml
    rules/obligation_dates.yaml  rules/applicability.yaml
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from verity_core.content.decisions import load_decisions
from verity_core.content.org import load_estate
from verity_core.content.schema import (
    ApplicabilityFile,
    ControlsFile,
    FrameworkFile,
    MappingsFile,
    ObligationDate,
    ObligationDatesFile,
)
from verity_core.content.yamlio import ContentError, parse, reading
from verity_core.model import ids
from verity_core.model.edges import Edge, MapsToEdge, PlainEdge
from verity_core.model.enums import EdgeType, Source
from verity_core.model.evidence import Evidence
from verity_core.model.nodes import Control, Framework, Node, Requirement

DEFAULT_TENANT = "kestrel"


@dataclass(frozen=True)
class Content:
    tenant: str
    frameworks: tuple[Framework, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    controls: tuple[Control, ...] = ()
    edges: tuple[Edge, ...] = ()
    dates: tuple[ObligationDate, ...] = ()
    rules: ApplicabilityFile | None = None
    # The fictional organisation and its AI estate, from `org/*.yaml`.
    estate: tuple[Node, ...] = ()
    # Human decisions from `decisions/*.yaml`, as Evidence (ADR 0019).
    decisions: tuple[Evidence, ...] = ()
    # Framework slugs whose text is copyrighted (ISO): IDs and original summaries only.
    copyrighted: frozenset[str] = frozenset()
    # Public pages that agree on each requirement's ID, by requirement ID.
    listing_sources: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def nodes(self) -> list[Node]:
        return [*self.frameworks, *self.requirements, *self.controls, *self.estate, *self.decisions]


def load_content(root: Path | str, *, tenant: str = DEFAULT_TENANT) -> Content:
    root = Path(root)
    common: dict[str, Any] = {"tenant": tenant, "source": Source.SEEDED}

    frameworks: list[Framework] = []
    requirements: list[Requirement] = []
    edges: list[Edge] = []
    copyrighted: set[str] = set()
    listing: dict[str, tuple[str, ...]] = {}
    requirement_ids: dict[str, dict[str, str]] = {}  # framework slug -> {requirement slug: ID}

    for path in sorted((root / "frameworks").glob("*.yaml")):
        parsed = parse(path, FrameworkFile)
        fw = parsed.framework
        with reading(path):
            if fw.slug in requirement_ids:
                raise ContentError(path, f"framework {fw.slug!r} is defined twice")
            requirement_ids[fw.slug] = {}
            fw_id = ids.framework_id(fw.slug)
            frameworks.append(
                Framework(
                    id=fw_id,
                    name=fw.name,
                    source_version=fw.source_version,
                    source_url=fw.source_url,
                    last_verified=fw.last_verified,
                    binding=fw.binding,
                    **common,
                )
            )
            if fw.copyrighted:
                copyrighted.add(fw.slug)
            for r in parsed.requirements:
                if r.id in requirement_ids[fw.slug]:
                    raise ContentError(path, f"requirement {r.id!r} is defined twice")
                req_id = ids.requirement_id(fw.slug, r.id)
                requirement_ids[fw.slug][r.id] = req_id
                requirements.append(
                    Requirement(
                        id=req_id,
                        ref=r.ref,
                        summary=r.summary,
                        source_url=r.source_url or fw.source_url,
                        source_version=r.source_version or fw.source_version,
                        last_verified=r.last_verified or fw.last_verified,
                        verified_against=r.verified_against,
                        **common,
                    )
                )
                listing[req_id] = tuple(r.listing_sources)
            parents = {r.id: r.parent for r in parsed.requirements}
            for r in parsed.requirements:
                if r.parent is not None and r.parent not in parents:
                    raise ContentError(path, f"{r.id!r} has unknown parent {r.parent!r}")
                if _has_cycle(r.id, parents):
                    raise ContentError(path, f"{r.id!r} is its own ancestor")
                dst = fw_id if r.parent is None else requirement_ids[fw.slug][r.parent]
                edges.append(
                    PlainEdge(
                        src=requirement_ids[fw.slug][r.id],
                        dst=dst,
                        type=EdgeType.PART_OF,
                        **common,
                    )
                )

    controls: list[Control] = []
    control_path = root / "controls.yaml"
    if control_path.exists():
        with reading(control_path):
            for c in parse(control_path, ControlsFile).controls:
                node_id = ids.control_id(c.code)
                if any(existing.id == node_id for existing in controls):
                    raise ContentError(control_path, f"control {c.code!r} is defined twice")
                controls.append(
                    Control(
                        id=node_id,
                        title=c.title,
                        summary=c.summary,
                        kind=c.kind,
                        automatable=c.automatable,
                        scope_level=c.scope_level,
                        **common,
                    )
                )
    control_ids = {c.id for c in controls}

    mapped: set[tuple[str, str]] = set()
    for path in sorted((root / "mappings").glob("*.yaml")):
        parsed_m = parse(path, MappingsFile)
        with reading(path):
            if parsed_m.framework not in requirement_ids:
                raise ContentError(path, f"unknown framework {parsed_m.framework!r}")
            for m in parsed_m.mappings:
                src = requirement_ids[parsed_m.framework].get(m.requirement)
                dst = ids.control_id(m.control)
                if src is None:
                    raise ContentError(path, f"unknown requirement {m.requirement!r}")
                if dst not in control_ids:
                    raise ContentError(path, f"unknown control {m.control!r}")
                if (src, dst) in mapped:
                    raise ContentError(path, f"{m.requirement!r} is mapped to {m.control!r} twice")
                mapped.add((src, dst))
                edges.append(
                    MapsToEdge(
                        src=src,
                        dst=dst,
                        strm=m.strm,
                        strength=m.strength,
                        rationale_type=m.rationale_type,
                        rationale=m.rationale,
                        sufficiency=m.sufficiency,
                        **common,
                    )
                )

    dates: list[ObligationDate] = []
    dates_path = root / "rules" / "obligation_dates.yaml"
    if dates_path.exists():
        dates = parse(dates_path, ObligationDatesFile).dates
        seen = [d.id for d in dates]
        duplicate = next((d for d in seen if seen.count(d) > 1), None)
        if duplicate is not None:
            raise ContentError(dates_path, f"date {duplicate!r} is defined twice")

    rules_path = root / "rules" / "applicability.yaml"
    rules = parse(rules_path, ApplicabilityFile) if rules_path.exists() else None
    if rules is not None:
        seen_rules = [r.id for r in rules.rules]
        repeated = next((r for r in seen_rules if seen_rules.count(r) > 1), None)
        if repeated is not None:
            raise ContentError(rules_path, f"rule {repeated!r} is defined twice")

    estate, estate_edges = load_estate(root, tenant, control_ids)
    decisions, decision_edges = load_decisions(root, tenant)

    return Content(
        tenant=tenant,
        frameworks=tuple(frameworks),
        requirements=tuple(requirements),
        controls=tuple(controls),
        edges=(*edges, *estate_edges, *decision_edges),
        estate=tuple(estate),
        decisions=tuple(decisions),
        dates=tuple(dates),
        rules=rules,
        copyrighted=frozenset(copyrighted),
        listing_sources=listing,
    )


def _has_cycle(start: str, parents: dict[str, str | None]) -> bool:
    seen = {start}
    current = parents.get(start)
    while current is not None:
        if current in seen:
            return True
        seen.add(current)
        current = parents.get(current)
    return False
