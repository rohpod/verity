"""How fresh a piece of evidence is at `as_of`. Pure, and derived on read (D5, ADR 0019).

Stale means past `valid_until`, or collected before a `ChangeEvent` that was detected by `as_of`
and hit the resource it came from. That second test is `stale_by_change` (ADR 0012), reused as
it is, so evidence collected after the change recovers the assessment.
"""

from datetime import datetime, timedelta
from enum import StrEnum

import networkx as nx

from verity_core.graph.loader import node_record
from verity_core.graph.traversals import stale_by_change
from verity_core.model.enums import NodeType
from verity_core.model.nodes import ChangeEvent, Evidence

EXPIRING_WITHIN = timedelta(days=7)


class Freshness(StrEnum):
    FRESH = "fresh"
    EXPIRING = "expiring"
    STALE = "stale"


def stale_evidence_ids(graph: nx.MultiDiGraph, as_of: datetime) -> frozenset[str]:
    """Evidence made stale by a change detected at or before `as_of`."""
    stale: set[str] = set()
    for node_id in sorted(graph.nodes):
        change = node_record(graph, node_id)
        if isinstance(change, ChangeEvent) and change.detected_at <= as_of:
            stale.update(item.evidence_id for item in stale_by_change(graph, change.id).evidence)
    return frozenset(stale)


def freshness(evidence: Evidence, as_of: datetime, stale_ids: frozenset[str]) -> Freshness:
    if as_of > evidence.valid_until or evidence.id in stale_ids:
        return Freshness.STALE
    if evidence.valid_until - as_of <= EXPIRING_WITHIN:
        return Freshness.EXPIRING
    return Freshness.FRESH


def evidence_in_graph(graph: nx.MultiDiGraph) -> list[Evidence]:
    found = (node_record(graph, n) for n in sorted(graph.nodes))
    return [n for n in found if isinstance(n, Evidence) and n.type is NodeType.EVIDENCE]
