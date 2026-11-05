"""Reads `org/*.yaml`: the fictional organisation, its people and its AI estate.

References (an owner, a model, a provider) may point into another file, so every file is read
and every record named before any edge is built. An edge takes the provenance of the record
that declares it, so a simulated model's `PROVIDED_BY` edge is simulated too.
"""

from dataclasses import dataclass
from pathlib import Path

from verity_core.content.schema import OrgFile, SystemIn
from verity_core.content.yamlio import ContentError, parse, reading
from verity_core.model import ids
from verity_core.model.edges import Edge, PlainEdge, ProcessesEdge
from verity_core.model.enums import EdgeType, Source
from verity_core.model.nodes import (
    AISystem,
    Dataset,
    Department,
    Model,
    Node,
    Organisation,
    Person,
    Policy,
    Provider,
    Risk,
)


@dataclass
class _Slugs:
    """Which record each slug names, across all files. A slug is unique within its kind."""

    kind: str
    ids: dict[str, str]

    def claim(self, path: Path, slug: str, node_id: str) -> None:
        if slug in self.ids:
            raise ContentError(path, f"{self.kind} {slug!r} is defined twice")
        self.ids[slug] = node_id

    def find(self, path: Path, slug: str, owner: str) -> str:
        if slug not in self.ids:
            raise ContentError(path, f"{owner} refers to unknown {self.kind} {slug!r}")
        return self.ids[slug]


def load_estate(root: Path, tenant: str) -> tuple[list[Node], list[Edge]]:
    files = [(p, parse(p, OrgFile)) for p in sorted((root / "org").glob("*.yaml"))]
    kinds = {
        name: _Slugs(name, {})
        for name in ("department", "person", "provider", "model", "dataset", "risk", "system")
    }
    nodes: list[Node] = []
    organisations: list[str] = []

    def source_of(file: OrgFile, item) -> Source:
        return item.source or file.source

    for path, f in files:
        with reading(path):
            if f.organisation is not None:
                org_id = ids.organisation_id(f.organisation.slug)
                organisations.append(org_id)
                nodes.append(
                    Organisation(
                        id=org_id,
                        name=f.organisation.name,
                        tenant=tenant,
                        source=source_of(f, f.organisation),
                    )
                )
            for d in f.departments:
                kinds["department"].claim(path, d.slug, ids.department_id(d.slug))
                nodes.append(
                    Department(
                        id=ids.department_id(d.slug),
                        name=d.name,
                        tenant=tenant,
                        source=source_of(f, d),
                    )
                )
            for person in f.people:
                kinds["person"].claim(path, person.slug, ids.person_id(person.slug))
                nodes.append(
                    Person(
                        id=ids.person_id(person.slug),
                        name=person.name,
                        job_title=person.job_title,
                        tenant=tenant,
                        source=source_of(f, person),
                    )
                )
            for prov in f.providers:
                kinds["provider"].claim(path, prov.slug, ids.provider_id(prov.slug))
                nodes.append(
                    Provider(
                        id=ids.provider_id(prov.slug),
                        name=prov.name,
                        simulated=prov.simulated,
                        tenant=tenant,
                        source=source_of(f, prov),
                    )
                )
            for m in f.models:
                kinds["model"].claim(path, m.slug, ids.model_id(m.slug))
                nodes.append(
                    Model(
                        id=ids.model_id(m.slug),
                        name=m.name,
                        origin=m.origin,
                        tenant=tenant,
                        source=source_of(f, m),
                    )
                )
            for ds in f.datasets:
                kinds["dataset"].claim(path, ds.slug, ids.dataset_id(ds.slug))
                nodes.append(
                    Dataset(
                        id=ids.dataset_id(ds.slug),
                        name=ds.name,
                        classification=ds.classification,
                        personal_data=ds.personal_data,
                        tenant=tenant,
                        source=source_of(f, ds),
                    )
                )
            for pol in f.policies:
                nodes.append(
                    Policy(
                        id=ids.policy_id(pol.slug),
                        title=pol.title,
                        summary=pol.summary,
                        tenant=tenant,
                        source=source_of(f, pol),
                    )
                )
            for r in f.risks:
                kinds["risk"].claim(path, r.slug, ids.risk_id(r.slug))
                nodes.append(
                    Risk(
                        id=ids.risk_id(r.slug),
                        title=r.title,
                        description=r.description,
                        tenant=tenant,
                        source=source_of(f, r),
                    )
                )
            for s in f.systems:
                kinds["system"].claim(path, s.slug, ids.system_id(s.slug))
                nodes.append(_system(s, tenant, source_of(f, s)))

    if len(organisations) > 1:
        raise ContentError(root / "org", "a tenant has exactly one organisation (ADR 0012)")
    if not organisations and any(f.departments for _, f in files):
        raise ContentError(root / "org", "departments need an organisation")

    edges: list[Edge] = []

    def edge(edge_type: EdgeType, src: str, dst: str, source: Source) -> None:
        edges.append(PlainEdge(src=src, dst=dst, type=edge_type, tenant=tenant, source=source))

    for path, f in files:
        with reading(path):
            for d in f.departments:
                edge(
                    EdgeType.PART_OF,
                    ids.department_id(d.slug),
                    organisations[0],
                    source_of(f, d),
                )
            for person in f.people:
                dept = kinds["department"].find(path, person.department, f"person {person.slug!r}")
                edge(EdgeType.MEMBER_OF, ids.person_id(person.slug), dept, source_of(f, person))
            for m in f.models:
                src, source = ids.model_id(m.slug), source_of(f, m)
                if m.provider is not None:
                    provider = kinds["provider"].find(path, m.provider, f"model {m.slug!r}")
                    edge(EdgeType.PROVIDED_BY, src, provider, source)
                for slug in m.trained_on:
                    dataset = kinds["dataset"].find(path, slug, f"model {m.slug!r}")
                    edge(EdgeType.TRAINED_ON, src, dataset, source)
            for r in f.risks:
                if r.owner is not None:
                    owner = kinds["person"].find(path, r.owner, f"risk {r.slug!r}")
                    edge(EdgeType.OWNS, owner, ids.risk_id(r.slug), source_of(f, r))
            for s in f.systems:
                _system_edges(path, s, source_of(f, s), kinds, edge, tenant, edges)

    return nodes, edges


def _system(s: SystemIn, tenant: str, source: Source) -> AISystem:
    return AISystem(
        id=ids.system_id(s.slug),
        name=s.name,
        purpose=s.purpose,
        kind=s.kind,
        roles=s.roles,
        use_domains=s.use_domains,
        interacts_with_people=s.interacts_with_people,
        generates_synthetic_content=s.generates_synthetic_content,
        first_placed_on_market=s.first_placed_on_market,
        tenant=tenant,
        source=source,
    )


def _system_edges(path, s, source, kinds, edge, tenant, edges) -> None:
    system = ids.system_id(s.slug)
    owner = f"system {s.slug!r}"
    if s.owner is not None:
        edge(EdgeType.OWNS, kinds["person"].find(path, s.owner, owner), system, source)
    for slug in s.developers:
        edge(EdgeType.DEVELOPS, kinds["person"].find(path, slug, owner), system, source)
    if s.risk_approver is not None:
        approver = kinds["person"].find(path, s.risk_approver, owner)
        edge(EdgeType.APPROVES_RISK_FOR, approver, system, source)
    for slug in s.models:
        edge(EdgeType.USES_MODEL, system, kinds["model"].find(path, slug, owner), source)
    for use in s.datasets:
        dataset = kinds["dataset"].find(path, use.dataset, owner)
        edges.append(
            ProcessesEdge(
                src=system, dst=dataset, purpose=use.purpose, tenant=tenant, source=source
            )
        )
    for slug in s.risks:
        edge(EdgeType.HAS_RISK, system, kinds["risk"].find(path, slug, owner), source)
