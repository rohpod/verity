"""The five core traversals (docs/architecture.md section E), as pure functions over the
graph from `load_graph`. They take no clock and call no repository.

They use explicit typed hops rather than a generic search, so an answer cannot leak to another
system through a shared requirement. They behave like left joins: a control with no
assessment, or an assessment with no evidence, still returns a row, because gaps are findings.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import networkx as nx

from verity_core.graph.loader import in_edges, node_record, out_edges
from verity_core.model.edges import AppliesToEdge, MapsToEdge
from verity_core.model.enums import (
    SCOPE_NODE_TYPE,
    AssuranceLevel,
    EdgeType,
    EvidenceKind,
    ImplementationStatus,
    ModelOrigin,
    NodeType,
    Role,
    ScopeLevel,
    Source,
    StrmType,
)
from verity_core.model.nodes import Control, ControlAssessment, Evidence, Model, Node


class Resolution(StrEnum):
    """How a control's assessment was found for a scope."""

    DIRECT = "direct"  # scoped to the system itself
    INHERITED_ORG = "inherited_org"  # the organisation's assessment
    INHERITED_PROVIDER = "inherited_provider"  # the model provider's assessment
    NOT_APPLICABLE = "not_applicable"  # provider-level control, but only in-house models (D13)
    PROVIDER_UNKNOWN = "provider_unknown"  # a provider should exist but is not recorded: a gap
    UNMAPPED = "unmapped"  # the requirement has no usable control mapping


@dataclass(frozen=True)
class _Target:
    resolution: Resolution
    provider_id: str | None
    scope_id: str | None  # whose assessment answers; None if there is no one to ask


# --- shared hops --------------------------------------------------------------------------


def _require(graph: nx.MultiDiGraph, node_id: str, *types: NodeType) -> Node:
    node = node_record(graph, node_id)
    if node is None or node.type not in types:
        wanted = " or ".join(types)
        raise ValueError(f"{node_id!r} is not a {wanted} in the graph")
    return node


def _organisation(graph: nx.MultiDiGraph) -> Node | None:
    """The tenant is the organisation (ADR 0012): there is at most one."""
    orgs = sorted(n for n in graph.nodes if graph.nodes[n]["record"].type is NodeType.ORGANISATION)
    return graph.nodes[orgs[0]]["record"] if orgs else None


def _provider_targets(graph: nx.MultiDiGraph, system_id: str) -> list[_Target]:
    """System, then model, then provider. Only a system whose models are all known to be
    in-house is `not_applicable` (D13). Anything else without a provider is a gap: no recorded
    model, or a third-party model with no PROVIDED_BY."""
    providers: set[str] = set()
    unknown = False
    models = out_edges(graph, system_id, EdgeType.USES_MODEL)
    for used in models:
        model = node_record(graph, used.dst)
        provided = out_edges(graph, used.dst, EdgeType.PROVIDED_BY)
        providers.update(e.dst for e in provided)
        if isinstance(model, Model) and model.origin is ModelOrigin.THIRD_PARTY and not provided:
            unknown = True
    targets = [_Target(Resolution.INHERITED_PROVIDER, p, p) for p in sorted(providers)]
    if unknown or not models:
        targets.append(_Target(Resolution.PROVIDER_UNKNOWN, None, None))
    return targets or [_Target(Resolution.NOT_APPLICABLE, None, None)]


def _targets(graph: nx.MultiDiGraph, scope: Node, control: Control) -> list[_Target]:
    """Whose assessment answers `control` for `scope`, by the control's scope level."""
    level = control.scope_level
    if scope.type is NodeType.AI_SYSTEM:
        if level is ScopeLevel.SYSTEM:
            return [_Target(Resolution.DIRECT, None, scope.id)]
        if level is ScopeLevel.ORGANISATION:
            org = _organisation(graph)
            return [_Target(Resolution.INHERITED_ORG, None, org.id if org else None)]
        return _provider_targets(graph, scope.id)
    if SCOPE_NODE_TYPE[level] is scope.type:
        return [_Target(Resolution.DIRECT, None, scope.id)]
    return [_Target(Resolution.NOT_APPLICABLE, None, None)]


def _assessment_for(graph: nx.MultiDiGraph, control_id: str, scope_id: str | None) -> str | None:
    if scope_id is None:
        return None
    for assesses in in_edges(graph, control_id, EdgeType.ASSESSES):
        if any(s.dst == scope_id for s in out_edges(graph, assesses.src, EdgeType.SCOPED_TO)):
            return assesses.src
    return None


def _evidence_ids(graph: nx.MultiDiGraph, assessment_id: str | None) -> tuple[str, ...]:
    if assessment_id is None:
        return ()
    return tuple(e.src for e in in_edges(graph, assessment_id, EdgeType.SUPPORTS))


def _usable_mappings(
    graph: nx.MultiDiGraph, requirement_id: str
) -> list[tuple[MapsToEdge, Control]]:
    """MAPS_TO edges that can carry an obligation. `no_relationship` is a recorded decision
    that a control does not help, so it contributes no control."""
    usable = []
    for mapping in out_edges(graph, requirement_id, EdgeType.MAPS_TO):
        control = node_record(graph, mapping.dst)
        if (
            isinstance(mapping, MapsToEdge)
            and mapping.strm is not StrmType.NO_RELATIONSHIP
            and isinstance(control, Control)
        ):
            usable.append((mapping, control))
    return usable


# --- 1. What applies to system S, and what proves it? --------------------------------------


@dataclass(frozen=True)
class ObligationRow:
    requirement_id: str
    role: Role
    applies_to: str  # the system or the organisation the requirement is aimed at
    control_id: str | None  # None when the requirement maps to no usable control
    mapping: MapsToEdge | None
    resolution: Resolution
    provider_id: str | None
    assessment_id: str | None  # None means no one has assessed this control: a gap
    evidence_ids: tuple[str, ...]  # empty means nothing proves it: a gap


def obligations_for(graph: nx.MultiDiGraph, system_id: str) -> list[ObligationRow]:
    """Every (requirement, role, control) that applies to the system or its organisation,
    with the assessment and evidence that answer it.

    `{S, Org} <-APPLIES_TO- Req -MAPS_TO-> Ctl <-ASSESSES- CA <-SUPPORTS- Evidence`, where the
    CA is scoped to S, the organisation or a provider, by the control's `scope_level`.
    """
    system = _require(graph, system_id, NodeType.AI_SYSTEM)
    org = _organisation(graph)
    rows: list[ObligationRow] = []
    for aim in [system.id, *([org.id] if org else [])]:
        for applies in in_edges(graph, aim, EdgeType.APPLIES_TO):
            assert isinstance(applies, AppliesToEdge)
            mappings = _usable_mappings(graph, applies.src)
            if not mappings:
                rows.append(
                    ObligationRow(
                        applies.src,
                        applies.role,
                        aim,
                        None,
                        None,
                        Resolution.UNMAPPED,
                        None,
                        None,
                        (),
                    )
                )
            for mapping, control in mappings:
                for target in _targets(graph, system, control):
                    assessment = _assessment_for(graph, control.id, target.scope_id)
                    rows.append(
                        ObligationRow(
                            applies.src,
                            applies.role,
                            aim,
                            control.id,
                            mapping,
                            target.resolution,
                            target.provider_id,
                            assessment,
                            _evidence_ids(graph, assessment),
                        )
                    )
    return sorted(
        rows,
        key=lambda r: (
            r.requirement_id,
            r.role.value,
            r.control_id or "",
            r.provider_id or "",
            r.applies_to,
        ),
    )


# --- 2. Impact of an incident at provider P -----------------------------------------------


@dataclass(frozen=True)
class SystemImpact:
    system_id: str
    model_ids: tuple[str, ...]  # this provider's models the system uses
    owner_ids: tuple[str, ...]
    risk_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]  # requirements aimed at this system itself


@dataclass(frozen=True)
class ProviderImpact:
    provider_id: str
    assessment_ids: tuple[str, ...]  # assessments scoped to the provider
    systems: tuple[SystemImpact, ...]


def provider_impact(graph: nx.MultiDiGraph, provider_id: str) -> ProviderImpact:
    """`P <-PROVIDED_BY- Model <-USES_MODEL- AISystem -> {owners, risks, requirements}`, plus
    the assessments scoped to P.

    Three hops from P at most. A system with only in-house models is never reached, and one
    system's requirements cannot lead to another, because every hop is typed.
    """
    _require(graph, provider_id, NodeType.PROVIDER)
    models = sorted(e.src for e in in_edges(graph, provider_id, EdgeType.PROVIDED_BY))
    used_by: dict[str, set[str]] = {}
    for model_id in models:
        for uses in in_edges(graph, model_id, EdgeType.USES_MODEL):
            used_by.setdefault(uses.src, set()).add(model_id)
    systems = tuple(
        SystemImpact(
            system_id=system_id,
            model_ids=tuple(sorted(used_by[system_id])),
            owner_ids=tuple(e.src for e in in_edges(graph, system_id, EdgeType.OWNS)),
            risk_ids=tuple(e.dst for e in out_edges(graph, system_id, EdgeType.HAS_RISK)),
            requirement_ids=tuple(
                sorted({e.src for e in in_edges(graph, system_id, EdgeType.APPLIES_TO)})
            ),
        )
        for system_id in sorted(used_by)
    )
    assessments = tuple(sorted(e.src for e in in_edges(graph, provider_id, EdgeType.SCOPED_TO)))
    return ProviderImpact(provider_id, assessments, systems)


# --- 3. Crosswalk: requirement R in one framework to another -------------------------------


@dataclass(frozen=True)
class DerivedLink:
    """Two requirements related through one hub control (D6).

    It has no STRM type, because composing two relationships does not give a third one that
    can be trusted. Both spokes are kept so the reader sees what each claims.
    """

    via_control_id: str
    target_requirement_id: str
    left: MapsToEdge  # the source requirement to the control
    right: MapsToEdge  # the target requirement to the control

    @property
    def strength(self) -> int:
        """The weaker of the two spokes."""
        return min(self.left.strength, self.right.strength)


def _in_framework(graph: nx.MultiDiGraph, requirement_id: str, framework_id: str) -> bool:
    """Is the requirement under the framework, through any chain of PART_OF?"""
    seen: set[str] = set()
    stack = [requirement_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        for part_of in out_edges(graph, current, EdgeType.PART_OF):
            if part_of.dst == framework_id:
                return True
            stack.append(part_of.dst)
    return False


def crosswalk(
    graph: nx.MultiDiGraph, requirement_id: str, target_framework_id: str
) -> list[DerivedLink]:
    """`R -MAPS_TO-> Ctl <-MAPS_TO- R'` where R' is under the target framework.

    A `no_relationship` spoke never composes, on either side.
    """
    _require(graph, requirement_id, NodeType.REQUIREMENT)
    _require(graph, target_framework_id, NodeType.FRAMEWORK)
    links = []
    for left, control in _usable_mappings(graph, requirement_id):
        for right in in_edges(graph, control.id, EdgeType.MAPS_TO):
            if (
                isinstance(right, MapsToEdge)
                and right.strm is not StrmType.NO_RELATIONSHIP
                and right.src != requirement_id
                and _in_framework(graph, right.src, target_framework_id)
            ):
                links.append(DerivedLink(control.id, right.src, left, right))
    return sorted(links, key=lambda link: (link.via_control_id, link.target_requirement_id))


# --- 4. Evidence made stale by a change ----------------------------------------------------


@dataclass(frozen=True)
class StaleEvidence:
    evidence_id: str
    resource_id: str
    assessment_ids: tuple[str, ...]  # the assessments this evidence supports


@dataclass(frozen=True)
class StaleImpact:
    change_id: str
    evidence: tuple[StaleEvidence, ...]

    @property
    def assessment_ids(self) -> tuple[str, ...]:
        return tuple(sorted({a for item in self.evidence for a in item.assessment_ids}))


def stale_by_change(graph: nx.MultiDiGraph, change_id: str) -> StaleImpact:
    """`ChangeEvent -AFFECTS-> Resource <-COLLECTED_FROM- Evidence -SUPPORTS-> CA`.

    Only evidence collected before the change was detected is stale (ADR 0012), so evidence
    collected afterwards recovers the assessment. Evidence not collected from the resource,
    such as a signed document or a person's attestation, is never touched.
    """
    change = _require(graph, change_id, NodeType.CHANGE_EVENT)
    found = []
    for affects in out_edges(graph, change.id, EdgeType.AFFECTS):
        for collected in in_edges(graph, affects.dst, EdgeType.COLLECTED_FROM):
            evidence = node_record(graph, collected.src)
            if isinstance(evidence, Evidence) and evidence.collected_at < change.detected_at:
                supports = tuple(
                    sorted(e.dst for e in out_edges(graph, evidence.id, EdgeType.SUPPORTS))
                )
                found.append(StaleEvidence(evidence.id, affects.dst, supports))
    found.sort(key=lambda item: (item.evidence_id, item.resource_id))
    return StaleImpact(change.id, tuple(found))


# --- 5. Audit trail -----------------------------------------------------------------------


@dataclass(frozen=True)
class AuditEvidence:
    evidence_id: str
    kind: EvidenceKind
    collector: str
    collected_at: datetime
    valid_until: datetime
    sha256: str
    source: Source


@dataclass(frozen=True)
class AuditLink:
    """One path from the requirement to its proof. An empty path is returned, not dropped."""

    control_id: str | None
    mapping: MapsToEdge | None
    resolution: Resolution
    provider_id: str | None
    assessment_id: str | None
    status: ImplementationStatus | None
    assurance_level: AssuranceLevel | None
    assessment_source: Source | None
    assessed_by: str | None  # the person on the ASSESSED edge
    signoff_source: Source | None  # `simulated` for a demo sign-off (D11)
    evidence: tuple[AuditEvidence, ...]


@dataclass(frozen=True)
class AuditTrail:
    requirement_id: str
    scope_id: str
    links: tuple[AuditLink, ...]


def audit_trail(graph: nx.MultiDiGraph, requirement_id: str, scope_id: str) -> AuditTrail:
    """`Req -> Ctl -> CA -> Evidence`, with hashes, collectors and the `ASSESSED` person.

    `scope_id` is a system (inherited organisation and provider assessments are followed, as in
    `obligations_for`), an organisation or a provider.
    """
    _require(graph, requirement_id, NodeType.REQUIREMENT)
    scope = _require(graph, scope_id, NodeType.AI_SYSTEM, NodeType.ORGANISATION, NodeType.PROVIDER)
    mappings = _usable_mappings(graph, requirement_id)
    links = [
        _link(graph, mapping, control, target)
        for mapping, control in mappings
        for target in _targets(graph, scope, control)
    ] or [AuditLink(None, None, Resolution.UNMAPPED, None, None, None, None, None, None, None, ())]
    links.sort(key=lambda link: (link.control_id or "", link.provider_id or ""))
    return AuditTrail(requirement_id, scope_id, tuple(links))


def _link(
    graph: nx.MultiDiGraph, mapping: MapsToEdge, control: Control, target: _Target
) -> AuditLink:
    assessment_id = _assessment_for(graph, control.id, target.scope_id)
    ca = node_record(graph, assessment_id) if assessment_id else None
    assert ca is None or isinstance(ca, ControlAssessment)
    assessed = in_edges(graph, assessment_id, EdgeType.ASSESSED) if assessment_id else []
    # The named assessor, if an edge records them, rather than whichever edge sorts first.
    signoff = next((e for e in assessed if ca and e.src == ca.assessor), None)
    signoff = signoff or (assessed[0] if assessed else None)
    evidence = sorted(
        (
            node
            for node in (node_record(graph, i) for i in _evidence_ids(graph, assessment_id))
            if isinstance(node, Evidence)
        ),
        key=lambda e: (e.collected_at, e.id),
    )
    return AuditLink(
        control_id=control.id,
        mapping=mapping,
        resolution=target.resolution,
        provider_id=target.provider_id,
        assessment_id=assessment_id,
        status=ca.status if ca else None,
        assurance_level=ca.assurance_level if ca else None,
        assessment_source=ca.source if ca else None,
        assessed_by=signoff.src if signoff else None,
        signoff_source=signoff.source if signoff else None,
        evidence=tuple(
            AuditEvidence(
                e.id, e.kind, e.collector, e.collected_at, e.valid_until, e.sha256, e.source
            )
            for e in evidence
        ),
    )
