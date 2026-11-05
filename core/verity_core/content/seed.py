"""Writes loaded content to a graph (M4, ADR 0008, ADR 0013).

Only through `GraphRepository`, so the same code seeds `InMemoryRepository` in tests and
`DynamoDBRepository` for real. Nodes go first because an edge is refused if an endpoint is
missing. Seeding twice writes nothing the second time: the repository skips unchanged records
(D14), and this module reports which records that was.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from verity_core.content.loader import Content
from verity_core.content.yamlio import ContentError
from verity_core.graph.repository import GraphRepository
from verity_core.model.enums import NodeType
from verity_core.model.evidence import Evidence

# Write units for the first write of a node or an edge (ADR 0016, measured on the real table):
# 4 on the table for each, plus 1 on GSI1 for a new node.
TABLE_UNITS_PER_RECORD = 4
INDEX_UNITS_PER_NODE = 1
TABLE_UNITS_PER_SECOND = 15  # the table's provisioned write capacity (ADR 0015)
INDEX_UNITS_PER_SECOND = 10

Progress = Callable[[str, int, int], None]  # (what, done, total)


@dataclass(frozen=True)
class SeedReport:
    nodes_written: int
    nodes_unchanged: int
    edges_written: int
    edges_unchanged: int

    @property
    def written(self) -> int:
        return self.nodes_written + self.edges_written


@dataclass(frozen=True)
class SeedEstimate:
    nodes: int
    edges: int
    table_units: int
    index_units: int

    @property
    def seconds(self) -> float:
        """How long the first seed takes at the provisioned capacity. The table is the limit."""
        return max(
            self.table_units / TABLE_UNITS_PER_SECOND, self.index_units / INDEX_UNITS_PER_SECOND
        )


def check_decisions(stored: Iterable[Evidence], content: Content) -> None:
    """A seeded decision is immutable (ADR 0020): refuse if one is gone from the content, or its
    file has changed. A correction is a new decision that supersedes it."""
    current = {ev.content["decision_id"]: ev.content["file_sha256"] for ev in content.decisions}
    for ev in stored:
        found = ev.content or {}
        if "decision_id" not in found or "decision_file" not in found:
            continue  # evidence that is not a decision
        decision_id = found["decision_id"]
        if current.get(decision_id) == found["file_sha256"]:
            continue
        where = Path(found["decision_file"])
        if decision_id in current:
            raise ContentError(
                where,
                f"decision_edited: {decision_id!r} was seeded and has changed. Restore it and add "
                f"a new decision with `supersedes: [{decision_id}]`",
            )
        raise ContentError(
            where,
            f"decision_removed: {decision_id!r} was seeded and its file is gone. Restore it and "
            f"add a decision of kind `revocation` with `supersedes: [{decision_id}]`",
        )


def estimate(content: Content) -> SeedEstimate:
    """The cost of a first seed. A re-seed writes almost nothing."""
    nodes, edges = len(content.nodes()), len(content.edges)
    return SeedEstimate(
        nodes=nodes,
        edges=edges,
        table_units=TABLE_UNITS_PER_RECORD * (nodes + edges),
        index_units=INDEX_UNITS_PER_NODE * nodes,
    )


def seed(
    repo: GraphRepository,
    content: Content,
    clock: Callable[[], datetime],
    progress: Progress | None = None,
) -> SeedReport:
    """Write every node, then every edge. `clock` must be the repository's own clock: a record
    counts as written when the repository stamped it at or after the start of this run."""
    check_decisions(repo.nodes_by_type(NodeType.EVIDENCE), content)  # before any write
    started = clock()
    report = progress or (lambda what, done, total: None)

    nodes = content.nodes()
    nodes_written = 0
    for done, node in enumerate(nodes, start=1):
        if repo.upsert_node(node).updated_at >= started:
            nodes_written += 1
        report("nodes", done, len(nodes))

    edges_written = 0
    for done, edge in enumerate(content.edges, start=1):
        if repo.upsert_edge(edge).updated_at >= started:
            edges_written += 1
        report("edges", done, len(content.edges))

    return SeedReport(
        nodes_written=nodes_written,
        nodes_unchanged=len(nodes) - nodes_written,
        edges_written=edges_written,
        edges_unchanged=len(content.edges) - edges_written,
    )
