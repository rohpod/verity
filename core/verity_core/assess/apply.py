"""Stores what `verity assess` derives, through `GraphRepository` only (ADR 0019, decision 5).

Stored: `APPLIES_TO` edges and ControlAssessments with their edges. Derived on read and never
stored: applicability status, freshness, requirement status and findings.

Steps:
1. Upsert the applicable edges, and close any derived `APPLIES_TO` edge no longer produced.
2. Reload the graph, so assessment sees the edges just written.
3. Upsert one ControlAssessment per control and scope, with `ASSESSES`, `SCOPED_TO`, `SUPPORTS`,
   and `ASSESSED` for L4. A `SUPPORTS` or `ASSESSED` edge the new assessment no longer produces
   is closed, so the graph never shows evidence that no longer decides it.

A re-run with nothing changed writes nothing: the repository skips unchanged records (D14), the
stored `assessed_at` is kept while status and level are unchanged, and only open edges are closed.
"""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

import networkx as nx

from verity_core.assess.controls import ControlAssessor, ControlResult
from verity_core.assess.findings import derive_findings
from verity_core.assess.requirements import RequirementStatus, requirement_statuses
from verity_core.content.schema import ApplicabilityFile, ObligationDate
from verity_core.graph.loader import in_edges, node_record
from verity_core.graph.memory import InMemoryRepository
from verity_core.graph.repository import GraphRepository
from verity_core.model import ids
from verity_core.model.edges import AppliesToEdge, Edge, PlainEdge
from verity_core.model.enums import AssuranceLevel, EdgeType, NodeType, Source
from verity_core.model.nodes import ControlAssessment, Node
from verity_core.rules.applicability import applicable_edges
from verity_core.rules.finding import Finding


class UnknownSystemError(ValueError):
    """`system_id` is not an AISystem in the graph."""


@dataclass(frozen=True)
class ApplyResult:
    written: Counter[str]  # records written, by kind
    unchanged_assessments: int
    statuses: tuple[RequirementStatus, ...]
    results: tuple[ControlResult, ...]
    findings: tuple[Finding, ...]

    @property
    def total_written(self) -> int:
        return sum(self.written.values())


def apply_assessment(
    repo: GraphRepository,
    rules: ApplicabilityFile,
    dates: Iterable[ObligationDate],
    as_of: datetime,
    clock: Callable[[], datetime],
    *,
    system_id: str | None = None,
) -> ApplyResult:
    """`clock` must be the repository's own, as in `seed`: a record counts as written when the
    repository stamped it at or after the start of this run. With `system_id`, only that
    system's and the organisation's `APPLIES_TO` edges are written or closed, and only the
    controls reachable from that system are assessed."""
    started = clock()
    written: Counter[str] = Counter()

    def note(kind: str, record: Node | Edge) -> None:
        if record.updated_at is not None and record.updated_at >= started:
            written[kind] += 1

    dates = list(dates)
    graph = repo.load_graph()
    systems = _ids_of(graph, NodeType.AI_SYSTEM)
    if system_id is not None and system_id not in systems:
        raise UnknownSystemError(f"{system_id!r} is not a system in the graph")
    organisation = next(iter(_ids_of(graph, NodeType.ORGANISATION)), None)
    in_scope = {system_id, organisation} if system_id else {*systems, organisation}
    in_scope.discard(None)

    # 1. applicable edges
    edges, applicability_findings = applicable_edges(graph, rules, dates, as_of)
    produced = {(e.src, e.dst, e.role) for e in edges}
    for edge in edges:
        if edge.dst in in_scope:
            note("applies_to", repo.upsert_edge(edge))
    for target in sorted(in_scope):
        for stored in in_edges(graph, target, EdgeType.APPLIES_TO):
            assert isinstance(stored, AppliesToEdge)
            key = (stored.src, stored.dst, stored.role)
            if stored.source is Source.DERIVED and key not in produced:
                closed = repo.close_edge(
                    stored.src,
                    EdgeType.APPLIES_TO,
                    stored.dst,
                    valid_to=clock(),
                    qualifier=stored.role.value,
                )
                note("applies_to_closed", closed)

    # 2. reload
    graph = repo.load_graph()

    # 3. assessments
    assessor = ControlAssessor(graph, as_of)
    statuses: list[RequirementStatus] = []
    for sid in [system_id] if system_id else systems:
        statuses.extend(requirement_statuses(graph, sid, assessor))
    results = assessor.results()
    for result in results:
        _store(repo, graph, result, as_of, clock, note)
    unchanged = len(results) - written["assessments"]
    findings = derive_findings(graph, as_of, results, statuses, applicability_findings)
    if system_id is not None:
        shown = {system_id, *(r.scope_id for r in results)}
        findings = [f for f in findings if f.subject in shown]
    return ApplyResult(written, unchanged, tuple(statuses), tuple(results), tuple(findings))


def _store(repo, graph, result: ControlResult, as_of, clock, note) -> None:
    """Write one ControlAssessment and its edges."""
    node_id = ids.ca_id(result.control_id, result.scope_id)
    tenant = node_record(graph, result.scope_id).tenant
    existing = repo.get_node(node_id)
    keep = (
        isinstance(existing, ControlAssessment)
        and existing.status is result.status
        and existing.assurance_level is result.level
    )
    node = ControlAssessment(
        id=node_id,
        status=result.status,
        assurance_level=result.level,
        method=result.method,
        assessed_at=existing.assessed_at if keep else as_of,
        assessor=result.assessor,
        tenant=tenant,
        source=result.source,
    )
    note("assessments", repo.upsert_node(node))

    def edge(edge_type: EdgeType, src: str, dst: str) -> None:
        note(
            "assessment_edges",
            repo.upsert_edge(
                PlainEdge(src=src, dst=dst, type=edge_type, tenant=tenant, source=result.source)
            ),
        )

    edge(EdgeType.ASSESSES, node_id, result.control_id)
    edge(EdgeType.SCOPED_TO, node_id, result.scope_id)
    wanted: dict[EdgeType, set[str]] = {EdgeType.SUPPORTS: set(), EdgeType.ASSESSED: set()}
    if result.evidence_id is not None:
        wanted[EdgeType.SUPPORTS].add(result.evidence_id)
        edge(EdgeType.SUPPORTS, result.evidence_id, node_id)
    if result.level is AssuranceLevel.L4_VERIFIED and result.assessor is not None:
        wanted[EdgeType.ASSESSED].add(result.assessor)
        edge(EdgeType.ASSESSED, result.assessor, node_id)
    for edge_type, keep_sources in wanted.items():
        for old in in_edges(graph, node_id, edge_type):
            if old.src not in keep_sources:
                note(
                    "assessment_edges_closed",
                    repo.close_edge(old.src, edge_type, node_id, valid_to=clock()),
                )


def _ids_of(graph: nx.MultiDiGraph, node_type: NodeType) -> list[str]:
    return [n for n in sorted(graph.nodes) if graph.nodes[n]["record"].type is node_type]


def estimate_apply(
    graph: nx.MultiDiGraph,
    rules: ApplicabilityFile,
    dates: Iterable[ObligationDate],
    as_of: datetime,
    clock: Callable[[], datetime],
    tenant: str,
    *,
    system_id: str | None = None,
) -> ApplyResult:
    """What `apply_assessment` would write to a repository holding `graph`, found by running
    it on an in-memory copy. Nothing real is touched."""
    copy = InMemoryRepository(tenant, clock)
    for node_id in sorted(graph.nodes):
        copy.upsert_node(graph.nodes[node_id]["record"])
    for _, _, data in sorted(graph.edges(data=True), key=lambda e: e[2]["record"].key.src):
        copy.upsert_edge(data["record"])
    return apply_assessment(copy, rules, dates, as_of, clock, system_id=system_id)
