"""The `GraphRepository` protocol (ADR 0003). All graph access goes through it, so features
never call DynamoDB directly and a graph database could replace it later.

A repository is bound to one tenant. Contract, shared by every implementation:

- Time comes from an injected clock. The repository stamps `created_at`, `updated_at`,
  `version` and, if absent, `valid_from`. Nothing here calls `now()` anywhere else.
- Re-upserting an unchanged record writes nothing, including no history entry (D14).
- Nodes must exist before the edges that connect them. Rule violations raise
  `GraphValidationError` and leave the graph untouched.
"""

from datetime import datetime
from typing import Protocol, runtime_checkable

from verity_core.model.edges import Edge
from verity_core.model.enums import Direction, EdgeType, NodeType
from verity_core.model.nodes import Node


@runtime_checkable
class GraphRepository(Protocol):
    def get_node(self, node_id: str) -> Node | None: ...

    def upsert_node(self, node: Node) -> Node:
        """Insert or update. A new node gets version 1. A real change bumps the version and
        adds a history entry; an unchanged node is returned as stored. Changing Evidence
        raises `ImmutableNodeError`."""
        ...

    def upsert_edge(self, edge: Edge) -> Edge:
        """Insert or update. Identity is `(src, type, dst, qualifier)`, so one system can
        have an APPLIES_TO edge per role."""
        ...

    def neighbors(
        self,
        node_id: str,
        direction: Direction,
        edge_type: EdgeType | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[Edge]:
        """Edges leaving (`OUT`) or arriving at (`IN`) a node, ordered by edge key. By default
        only open edges; with `as_of`, edges that existed at that time."""
        ...

    def nodes_by_type(self, node_type: NodeType) -> list[Node]:
        """Ordered by ID."""
        ...

    def history(self, node_id: str) -> list[Node]:
        """Every real version, oldest first, including the current one."""
        ...
