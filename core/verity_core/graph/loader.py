"""Build the NetworkX graph that traversals run on (ADR 0003). Both repositories call
`build_graph`, so they cannot disagree about what the graph contains.

Each node has a `record` attribute holding its pydantic node. Each edge has a `record`
attribute and the key `(type, qualifier)`, so the two APPLIES_TO roles between one pair of
nodes stay separate edges.
"""

from collections.abc import Iterable
from datetime import datetime

import networkx as nx

from verity_core.model.edges import Edge
from verity_core.model.enums import EdgeType
from verity_core.model.nodes import Node


def build_graph(
    nodes: Iterable[Node], edges: Iterable[Edge], *, as_of: datetime | None = None
) -> nx.MultiDiGraph:
    """Keep what is open now (`as_of=None`) or was valid at `as_of`. A node outside its
    validity is dropped together with its edges, and so is any edge whose endpoint is missing."""
    if as_of is not None and as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    graph = nx.MultiDiGraph()
    for node in sorted(nodes, key=lambda n: n.id):
        if node.is_active(as_of):
            graph.add_node(node.id, record=node)
    for edge in sorted(edges, key=lambda e: _sort_key(e)):
        if edge.is_active(as_of) and edge.src in graph and edge.dst in graph:
            graph.add_edge(edge.src, edge.dst, key=(edge.type, edge.qualifier), record=edge)
    return graph


def _sort_key(edge: Edge) -> tuple[str, str, str, str]:
    return (edge.src, edge.type.value, edge.dst, edge.qualifier or "")


# Typed hops for traversals and checks. Results are ordered, so output is deterministic.


def node_record(graph: nx.MultiDiGraph, node_id: str) -> Node | None:
    return graph.nodes[node_id]["record"] if node_id in graph else None


def out_edges(
    graph: nx.MultiDiGraph, node_id: str, edge_type: EdgeType | None = None
) -> list[Edge]:
    if node_id not in graph:
        return []
    found = (data["record"] for _, _, data in graph.out_edges(node_id, data=True))
    return sorted((e for e in found if edge_type in (None, e.type)), key=_sort_key)


def in_edges(graph: nx.MultiDiGraph, node_id: str, edge_type: EdgeType | None = None) -> list[Edge]:
    if node_id not in graph:
        return []
    found = (data["record"] for _, _, data in graph.in_edges(node_id, data=True))
    return sorted((e for e in found if edge_type in (None, e.type)), key=_sort_key)
