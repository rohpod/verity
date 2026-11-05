"""`InMemoryRepository`: tests and local development. `DynamoDBRepository` must behave
identically, which the shared contract suite checks. Every write decision comes from
`planning.py`; this class only stores the result."""

from collections.abc import Callable
from datetime import datetime

import networkx as nx
from pydantic import BaseModel

from verity_core.graph.errors import EdgeNotFoundError
from verity_core.graph.loader import build_graph, version_at
from verity_core.graph.planning import (
    WriteAction,
    check_usage_bounds,
    edges_to_close,
    ensure_tenant,
    neighbor_sort_key,
    plan_close_edge,
    plan_edge_write,
    plan_node_write,
    read_clock,
    require_aware,
    usage_identity,
)
from verity_core.model.edges import Edge, EdgeKey
from verity_core.model.enums import Direction, EdgeType, NodeType
from verity_core.model.nodes import Node
from verity_core.model.usage import UsageRecord
from verity_core.model.validation import validate_edge, validate_node_change


def _copy[R: BaseModel](record: R) -> R:
    """Frozen models still hold mutable dicts and lists, so reads hand out deep copies."""
    return record.model_copy(deep=True)


class InMemoryRepository:
    def __init__(self, tenant: str, clock: Callable[[], datetime]):
        self.tenant = tenant
        self._clock = clock
        self._nodes: dict[str, Node] = {}
        self._history: dict[str, list[Node]] = {}
        self._edges: dict[EdgeKey, Edge] = {}
        self._out: dict[str, set[EdgeKey]] = {}
        self._in: dict[str, set[EdgeKey]] = {}
        self._usage: dict[str, dict[tuple[datetime, str], UsageRecord]] = {}

    # --- nodes ---------------------------------------------------------------------------

    def get_node(self, node_id: str) -> Node | None:
        node = self._nodes.get(node_id)
        return _copy(node) if node else None

    def upsert_node(self, node: Node) -> Node:
        ensure_tenant(self.tenant, node.tenant, repr(node.id))
        validate_node_change(
            node,
            open_edges=self._open_edges_touching(node.id),
            organisation_ids=[n.id for n in self.nodes_by_type(NodeType.ORGANISATION)],
        )
        plan = plan_node_write(self._nodes.get(node.id), node, read_clock(self._clock))
        stored = plan.node
        if plan.action is not WriteAction.NOOP:
            self._nodes[stored.id] = stored
            self._history.setdefault(stored.id, []).append(stored)
            if stored.valid_to is not None:
                self._close_edges_of(stored)
        return _copy(stored)

    def _close_edges_of(self, node: Node) -> None:
        """An ended node takes its edges with it, so `neighbors` and `load_graph` agree."""
        for edge, valid_to in edges_to_close(node, self._open_edges_touching(node.id)):
            self.close_edge(
                edge.src, edge.type, edge.dst, valid_to=valid_to, qualifier=edge.qualifier
            )

    def nodes_by_type(self, node_type: NodeType) -> list[Node]:
        found = (n for n in self._nodes.values() if n.type is node_type)
        return [_copy(n) for n in sorted(found, key=lambda n: n.id)]

    def history(self, node_id: str) -> list[Node]:
        return [_copy(n) for n in self._history.get(node_id, [])]

    # --- edges ---------------------------------------------------------------------------

    def upsert_edge(self, edge: Edge) -> Edge:
        ensure_tenant(self.tenant, edge.tenant, f"{edge.type} edge")
        validate_edge(
            edge,
            self._nodes.get(edge.src),
            self._nodes.get(edge.dst),
            open_out_edges=self.neighbors(edge.src, Direction.OUT),
        )
        plan = plan_edge_write(self._edges.get(edge.key), edge, read_clock(self._clock))
        return self._store_edge(plan.edge, plan.action)

    def _store_edge(self, edge: Edge, action: WriteAction) -> Edge:
        if action is not WriteAction.NOOP:
            self._edges[edge.key] = edge
            self._out.setdefault(edge.src, set()).add(edge.key)
            self._in.setdefault(edge.dst, set()).add(edge.key)
        return _copy(edge)

    def close_edge(
        self,
        src: str,
        edge_type: EdgeType,
        dst: str,
        *,
        valid_to: datetime,
        qualifier: str | None = None,
    ) -> Edge:
        require_aware(valid_to, "valid_to must be timezone-aware")
        existing = self._edges.get(EdgeKey(src, edge_type, dst, qualifier))
        if existing is None:
            raise EdgeNotFoundError(f"no {edge_type} edge from {src!r} to {dst!r} ({qualifier})")
        plan = plan_close_edge(existing, valid_to, read_clock(self._clock))
        return self._store_edge(plan.edge, plan.action)

    def neighbors(
        self,
        node_id: str,
        direction: Direction,
        edge_type: EdgeType | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[Edge]:
        index = self._out if direction is Direction.OUT else self._in
        keys = sorted(index.get(node_id, ()), key=lambda k: neighbor_sort_key(k, direction))
        edges = (self._edges[k] for k in keys)
        return [
            _copy(e)
            for e in edges
            if (edge_type is None or e.type is edge_type) and e.is_active(as_of)
        ]

    def _open_edges_touching(self, node_id: str) -> list[Edge]:
        return self.neighbors(node_id, Direction.OUT) + self.neighbors(node_id, Direction.IN)

    def load_graph(self, *, as_of: datetime | None = None) -> nx.MultiDiGraph:
        if as_of is not None and as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        nodes = (
            self._nodes.values()
            if as_of is None
            else [version_at(versions, as_of) for versions in self._history.values()]
        )
        return build_graph(
            [_copy(n) for n in nodes], [_copy(e) for e in self._edges.values()], as_of=as_of
        )

    # --- usage ---------------------------------------------------------------------------

    def append_usage(self, record: UsageRecord) -> None:
        ensure_tenant(self.tenant, record.tenant, "usage record")
        self._usage.setdefault(record.system_id, {}).setdefault(usage_identity(record), record)

    def usage_records(
        self,
        system_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[UsageRecord]:
        check_usage_bounds(since, until)
        records = (self._usage.get(system_id) or {}).items()
        return [
            record
            for (stamp, _), record in sorted(records, key=lambda item: item[0])
            if (since is None or stamp >= since) and (until is None or stamp < until)
        ]
