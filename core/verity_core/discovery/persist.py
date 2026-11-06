"""The only writer of the discovery pipeline (ADR 0021, decisions 1, 6 and 19).

It writes through `GraphRepository` only, and only the node and edge types the crawler owns.
It never writes an `AISystem`, so the facts seeded in M4 cannot be overwritten. The order is
chosen so that a run which fails half way is repaired by the next one:

1. the `DiscoveryRun`, without `finished_at`;
2. each `ChangeEvent` and its `AFFECTS` edge, before the node changes, so a crash cannot lose
   the change;
3. resources (roles and tables, then functions), and `OBSERVED` for new and changed ones;
4. `RUNS_ON`, `ASSUMES` and `CALLS`, and the closing of those this run did not produce;
5. Candidates with `DERIVED_FROM` and `PROMOTED_TO`, and the ending of those that stopped
   qualifying;
6. Evidence with `ABOUT` and `COLLECTED_FROM`;
7. the ending of resources this run did not see;
8. the `DiscoveryRun` again, with `finished_at` and its summary.

An unfinished run keeps `finished_at` empty, which is the signal that it failed.
"""

from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime

from verity_core.graph.repository import GraphRepository
from verity_core.model.edges import Edge, PlainEdge
from verity_core.model.enums import EdgeType, NodeType
from verity_core.model.evidence import Evidence
from verity_core.model.nodes import AWSResource, Candidate, ChangeEvent, DiscoveryRun, Node

WRITABLE_NODES = frozenset(
    {
        NodeType.AWS_RESOURCE,
        NodeType.CANDIDATE,
        NodeType.DISCOVERY_RUN,
        NodeType.CHANGE_EVENT,
        NodeType.EVIDENCE,
    }
)
WRITABLE_EDGES = frozenset(
    {
        EdgeType.RUNS_ON,
        EdgeType.ASSUMES,
        EdgeType.CALLS,
        EdgeType.OBSERVED,
        EdgeType.AFFECTS,
        EdgeType.DERIVED_FROM,
        EdgeType.PROMOTED_TO,
        EdgeType.ABOUT,
        EdgeType.COLLECTED_FROM,
    }
)


class ForbiddenWriteError(ValueError):
    """The plan holds a node or edge type the crawler may not write. Nothing was written."""


@dataclass
class Plan:
    """Everything one run will write, decided before any write."""

    run: DiscoveryRun
    started: datetime
    summary: dict[str, int]
    changes: list[tuple[ChangeEvent, PlainEdge]] = field(default_factory=list)
    roles_and_tables: list[AWSResource] = field(default_factory=list)
    functions: list[AWSResource] = field(default_factory=list)
    observed: list[PlainEdge] = field(default_factory=list)
    relations: list[Edge] = field(default_factory=list)  # RUNS_ON, ASSUMES, CALLS
    stale_relations: list[Edge] = field(default_factory=list)  # open ones to close
    candidates: list[Candidate] = field(default_factory=list)
    candidate_edges: list[Edge] = field(default_factory=list)  # DERIVED_FROM, PROMOTED_TO
    stale_candidate_edges: list[Edge] = field(default_factory=list)
    ended_candidates: list[Candidate] = field(default_factory=list)
    evidence: list[tuple[Evidence, list[Edge]]] = field(default_factory=list)
    ended_resources: list[AWSResource] = field(default_factory=list)

    def nodes(self) -> Iterator[Node]:
        yield self.run
        yield from (change for change, _ in self.changes)
        yield from (*self.roles_and_tables, *self.functions)
        yield from (*self.candidates, *self.ended_candidates, *self.ended_resources)
        yield from (item for item, _ in self.evidence)

    def edges(self) -> Iterator[Edge]:
        yield from (edge for _, edge in self.changes)
        yield from (*self.observed, *self.relations, *self.stale_relations)
        yield from (*self.candidate_edges, *self.stale_candidate_edges)
        for _, edges in self.evidence:
            yield from edges


def check_writable(plan: Plan) -> None:
    for node in plan.nodes():
        if node.type not in WRITABLE_NODES:
            raise ForbiddenWriteError(f"the crawler may not write a {node.type} ({node.id})")
    for edge in plan.edges():
        if edge.type not in WRITABLE_EDGES:
            raise ForbiddenWriteError(f"the crawler may not write a {edge.type} edge")


def persist(
    repo: GraphRepository, plan: Plan, clock: Callable[[], datetime]
) -> tuple[Counter[str], DiscoveryRun]:
    """Write the plan. `clock` must be the repository's own, as in `seed`: a record counts as
    written when the repository stamped it at or after the start of the run."""
    check_writable(plan)
    started = plan.started
    written: Counter[str] = Counter()

    def note(kind: str, record: Node | Edge) -> None:
        if record.updated_at is not None and record.updated_at >= started:
            written[kind] += 1

    repo.upsert_node(plan.run)  # 1

    for change, affects in plan.changes:  # 2
        note("changes", repo.upsert_node(change))
        note("change_edges", repo.upsert_edge(affects))

    for resource in (*plan.roles_and_tables, *plan.functions):  # 3
        note("resources", repo.upsert_node(resource))
    for edge in plan.observed:
        note("observed", repo.upsert_edge(edge))

    for edge in plan.relations:  # 4
        note("relations", repo.upsert_edge(edge))
    for old in plan.stale_relations:
        note("relations_closed", _close(repo, old, started))

    for candidate in plan.candidates:  # 5
        note("candidates", repo.upsert_node(candidate))
    for edge in plan.candidate_edges:
        note("candidate_edges", repo.upsert_edge(edge))
    for old in plan.stale_candidate_edges:
        note("candidate_edges_closed", _close(repo, old, started))
    for ended in plan.ended_candidates:
        note("candidates_ended", repo.upsert_node(ended))

    for item, edges in plan.evidence:  # 6
        note("evidence", repo.upsert_node(item))
        for edge in edges:
            note("evidence_edges", repo.upsert_edge(edge))

    for gone in plan.ended_resources:  # 7
        note("resources_ended", repo.upsert_node(gone))

    finished = plan.run.model_copy(update={"finished_at": clock(), "summary": plan.summary})  # 8
    final = repo.upsert_node(finished)
    note("runs", final)
    return written, final  # type: ignore[return-value]


def _close(repo: GraphRepository, edge: Edge, valid_to: datetime) -> Edge:
    return repo.close_edge(
        edge.src, edge.type, edge.dst, valid_to=valid_to, qualifier=edge.qualifier
    )
