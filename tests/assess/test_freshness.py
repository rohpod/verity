from datetime import timedelta

import pytest
from assess_support import AS_OF, EARLIER, evidence, resource_and_change, verification
from verity_core.assess.freshness import (
    EXPIRING_WITHIN,
    Freshness,
    freshness,
    stale_evidence_ids,
)
from verity_core.graph.loader import build_graph
from verity_core.model.enums import EvidenceKind


def at(valid_until):
    return verification("VC-001", valid_until=valid_until)


def test_expiring_means_seven_days_or_less_remain():
    assert timedelta(days=7) == EXPIRING_WITHIN
    day = timedelta(days=1)
    assert freshness(at(AS_OF + 8 * day), AS_OF, frozenset()) is Freshness.FRESH
    assert freshness(at(AS_OF + 7 * day + timedelta(seconds=1)), AS_OF, frozenset()) is (
        Freshness.FRESH
    )
    assert freshness(at(AS_OF + 7 * day), AS_OF, frozenset()) is Freshness.EXPIRING
    assert freshness(at(AS_OF + day), AS_OF, frozenset()) is Freshness.EXPIRING


def test_at_valid_until_it_is_expiring_and_a_moment_later_stale():
    assert freshness(at(AS_OF), AS_OF, frozenset()) is Freshness.EXPIRING
    ev = at(AS_OF)
    assert freshness(ev, AS_OF + timedelta(microseconds=1), frozenset()) is Freshness.STALE


def test_evidence_named_stale_is_stale_whatever_its_date():
    ev = at(AS_OF + timedelta(days=90))
    assert freshness(ev, AS_OF, frozenset({ev.id})) is Freshness.STALE


@pytest.mark.parametrize(
    ("detected_after_collection", "stale"), [(timedelta(seconds=1), True), (timedelta(0), False)]
)
def test_a_change_detected_after_collection_makes_it_stale(detected_after_collection, stale):
    ev = evidence("VC-001", EvidenceKind.CONFIG_SNAPSHOT, collector="crawler@0.1.0")
    nodes, edges = resource_and_change(EARLIER + detected_after_collection, ev)
    graph = build_graph([ev, *nodes], edges)
    assert (ev.id in stale_evidence_ids(graph, AS_OF)) is stale


def test_a_change_after_as_of_makes_nothing_stale():
    ev = evidence("VC-001", EvidenceKind.CONFIG_SNAPSHOT, collector="crawler@0.1.0")
    nodes, edges = resource_and_change(AS_OF + timedelta(seconds=1), ev)
    graph = build_graph([ev, *nodes], edges)
    assert stale_evidence_ids(graph, AS_OF) == frozenset()
