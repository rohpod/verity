"""`InMemoryRepository`: tests and local development. `DynamoDBRepository` (M2) must behave
identically, which the shared contract suite checks."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from verity_core.graph.errors import EdgeClosedError, ImmutableNodeError, TenantMismatchError
from verity_core.model.edges import Edge, EdgeKey
from verity_core.model.enums import Direction, EdgeType, NodeType
from verity_core.model.evidence import Evidence
from verity_core.model.hashing import content_hash
from verity_core.model.nodes import Node
from verity_core.model.validation import validate_edge, validate_node_change


def _sort_key(key: EdgeKey) -> tuple[str, str, str, str]:
    return (key.src, key.type.value, key.dst, key.qualifier or "")


def _with[R: BaseModel](record: R, **updates: Any) -> R:
    """Copy with changes, validated again (for example `valid_to` must not precede `valid_from`)."""
    return type(record).model_validate({**record.model_dump(), **updates})


class InMemoryRepository:
    def __init__(self, tenant: str, clock: Callable[[], datetime]):
        self.tenant = tenant
        self._clock = clock
        self._nodes: dict[str, Node] = {}
        self._history: dict[str, list[Node]] = {}
        self._edges: dict[EdgeKey, Edge] = {}
        self._out: dict[str, set[EdgeKey]] = {}
        self._in: dict[str, set[EdgeKey]] = {}

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("the clock must return timezone-aware datetimes")
        return now.astimezone(UTC)

    # --- nodes ---------------------------------------------------------------------------

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def upsert_node(self, node: Node) -> Node:
        if node.tenant != self.tenant:
            raise TenantMismatchError(
                f"{node.id!r} is in tenant {node.tenant!r}, not {self.tenant!r}"
            )
        existing = self._nodes.get(node.id)
        validate_node_change(
            node,
            open_edges=self._open_edges_touching(node.id),
            organisation_ids=[n.id for n in self.nodes_by_type(NodeType.ORGANISATION)],
        )
        now = self._now()

        if existing is None:
            stored = _with(node, created_at=now, updated_at=now, version=1)
            if stored.valid_from is None:
                stored = _with(stored, valid_from=now)
        else:
            # A caller that does not know `valid_from` leaves it unset; keep the stored one.
            candidate = node if node.valid_from else _with(node, valid_from=existing.valid_from)
            if content_hash(candidate) == content_hash(existing):
                return existing
            if isinstance(existing, Evidence):
                raise ImmutableNodeError(f"{node.id!r} is Evidence; collect new evidence instead")
            stored = _with(
                candidate,
                created_at=existing.created_at,
                updated_at=now,
                version=existing.version + 1,
            )

        self._nodes[stored.id] = stored
        self._history.setdefault(stored.id, []).append(stored)
        return stored

    def nodes_by_type(self, node_type: NodeType) -> list[Node]:
        return sorted((n for n in self._nodes.values() if n.type is node_type), key=lambda n: n.id)

    def history(self, node_id: str) -> list[Node]:
        return list(self._history.get(node_id, []))

    # --- edges ---------------------------------------------------------------------------

    def upsert_edge(self, edge: Edge) -> Edge:
        if edge.tenant != self.tenant:
            raise TenantMismatchError(
                f"{edge.type} edge is in tenant {edge.tenant!r}, not {self.tenant!r}"
            )
        validate_edge(
            edge,
            self._nodes.get(edge.src),
            self._nodes.get(edge.dst),
            open_out_edges=self._edges_from(edge.src, as_of=None),
        )
        now = self._now()
        existing = self._edges.get(edge.key)

        if existing is None:
            stored = _with(edge, created_at=now, updated_at=now, version=1)
            if stored.valid_from is None:
                stored = _with(stored, valid_from=now)
        else:
            if existing.valid_to is not None:
                raise EdgeClosedError(f"{edge.key} is closed")
            candidate = _with(
                edge,
                valid_from=edge.valid_from or existing.valid_from,
                closed_intervals=existing.closed_intervals,
            )
            if content_hash(candidate) == content_hash(existing):
                return existing
            stored = _with(
                candidate,
                created_at=existing.created_at,
                updated_at=now,
                version=existing.version + 1,
            )

        self._edges[stored.key] = stored
        self._out.setdefault(stored.src, set()).add(stored.key)
        self._in.setdefault(stored.dst, set()).add(stored.key)
        return stored

    def neighbors(
        self,
        node_id: str,
        direction: Direction,
        edge_type: EdgeType | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[Edge]:
        index = self._out if direction is Direction.OUT else self._in
        keys = sorted(index.get(node_id, ()), key=_sort_key)
        edges = (self._edges[k] for k in keys)
        return [
            e for e in edges if (edge_type is None or e.type is edge_type) and e.is_active(as_of)
        ]

    def _edges_from(self, node_id: str, *, as_of: datetime | None) -> list[Edge]:
        return self.neighbors(node_id, Direction.OUT, as_of=as_of)

    def _open_edges_touching(self, node_id: str) -> list[Edge]:
        return self.neighbors(node_id, Direction.OUT) + self.neighbors(node_id, Direction.IN)
