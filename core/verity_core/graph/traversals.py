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
    NodeType,
    Role,
    ScopeLevel,
    Source,
    StrmType,
)
from verity_core.model.nodes import Control, ControlAssessment, Evidence, Node


class Resolution(StrEnum):
    """How a control's assessment was found for a scope."""

    DIRECT = "direct"  # scoped to the system itself
    INHERITED_ORG = "inherited_org"  # the organisation's assessment
    INHERITED_PROVIDER = "inherited_provider"  # the model provider's assessment
    NOT_APPLICABLE = "not_applicable"  # provider-level control, but no provider (D13)
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


def _providers_of(graph: nx.MultiDiGraph, system_id: str) -> list[str]:
    """System, then model, then provider. An in-house model has none."""
    found = {
        provided.dst
        for used in out_edges(graph, system_id, EdgeType.USES_MODEL)
        for provided in out_edges(graph, used.dst, EdgeType.PROVIDED_BY)
    }
    return sorted(found)


def _targets(graph: nx.MultiDiGraph, scope: Node, control: Control) -> list[_Target]:
    """Whose assessment answers `control` for `scope`, by the control's scope level."""
    level = control.scope_level
    if scope.type is NodeType.AI_SYSTEM:
        if level is ScopeLevel.SYSTEM:
            return [_Target(Resolution.DIRECT, None, scope.id)]
        if level is ScopeLevel.ORGANISATION:
            org = _organisation(graph)
            return [_Target(Resolution.INHERITED_ORG, None, org.id if org else None)]
        providers = _providers_of(graph, scope.id)
        if not providers:
            return [_Target(Resolution.NOT_APPLICABLE, None, None)]
        return [_Target(Resolution.INHERITED_PROVIDER, p, p) for p in providers]
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
    assessed = in_edges(graph, assessment_id, EdgeType.ASSESSED)[:1] if assessment_id else []
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
        assessed_by=assessed[0].src if assessed else None,
        signoff_source=assessed[0].source if assessed else None,
        evidence=tuple(
            AuditEvidence(
                e.id, e.kind, e.collector, e.collected_at, e.valid_until, e.sha256, e.source
            )
            for e in evidence
        ),
    )
