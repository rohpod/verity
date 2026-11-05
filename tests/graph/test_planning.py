"""The write rules on their own, with an explicit `now`. Both repositories apply these
plans, so they are what the DynamoDB repository must also obey (ADR 0013)."""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from factories import COMMON, T0, evidence, make_edge, one_of_each
from verity_core.graph import planning
from verity_core.graph.errors import ImmutableNodeError, TenantMismatchError
from verity_core.graph.planning import (
    WriteAction,
    check_usage_bounds,
    edges_to_close,
    ensure_tenant,
    period_start,
    plan_close_edge,
    plan_edge_write,
    plan_node_write,
    read_clock,
    reject_future_end,
    usage_identity,
    with_changes,
)
from verity_core.model.enums import EdgeType, NodeType, Source
from verity_core.model.usage import UsageRecord

SYSTEM = one_of_each()[NodeType.AI_SYSTEM]
OWNS = ("person:a-singh", "sys:talent-screening")


def day(n: int) -> datetime:
    return T0 + timedelta(days=n)


def owns(**overrides):
    return make_edge(EdgeType.OWNS, *OWNS, **overrides)


def stored_edge(**overrides):
    """An edge as the repository would have stored it on day 0."""
    return plan_edge_write(None, owns(**overrides), day(0)).edge


# --- helpers --------------------------------------------------------------------------------


def test_read_clock_calls_the_clock_once_and_returns_utc():
    calls = []

    def clock():
        calls.append(1)
        return datetime(2026, 11, 5, 11, 0, tzinfo=timezone(timedelta(hours=2)))

    assert read_clock(clock) == datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
    assert len(calls) == 1
    assert read_clock(clock).utcoffset() == timedelta(0)


def test_read_clock_refuses_a_naive_time():
    with pytest.raises(ValueError, match="timezone-aware"):
        read_clock(lambda: datetime(2026, 11, 5))


def test_ensure_tenant():
    ensure_tenant("kestrel", "kestrel", "x")
    with pytest.raises(TenantMismatchError, match="'other'"):
        ensure_tenant("kestrel", "other", "x")


def test_reject_future_end_allows_now_and_the_past():
    reject_future_end(None, day(0))
    reject_future_end(day(0), day(0))
    reject_future_end(day(-1), day(0))
    with pytest.raises(ValueError, match="future"):
        reject_future_end(day(1), day(0))


def test_with_changes_validates_again():
    assert with_changes(SYSTEM, version=3).version == 3
    with pytest.raises(ValueError):
        with_changes(SYSTEM, valid_from=day(2), valid_to=day(1))


def test_period_start_replaces_an_absent_or_stale_start():
    assert period_start(owns(valid_from=day(5)), None, day(9)) == day(5)
    assert period_start(owns(), None, day(9)) == day(9)
    assert period_start(owns(valid_from=day(1)), day(3), day(9)) == day(9)
    assert period_start(owns(valid_from=day(3)), day(3), day(9)) == day(3)


# --- nodes ----------------------------------------------------------------------------------


def test_a_new_node_is_stamped_and_inserted():
    plan = plan_node_write(None, SYSTEM, day(0))
    assert plan.action is WriteAction.INSERT
    assert plan.node.version == 1
    assert plan.node.created_at == plan.node.updated_at == plan.node.valid_from == day(0)
    assert SYSTEM.version == 0  # the input is never changed


def test_a_supplied_valid_from_is_kept_on_insert():
    plan = plan_node_write(None, SYSTEM.model_copy(update={"valid_from": day(-30)}), day(0))
    assert plan.node.valid_from == day(-30)


def test_an_unchanged_node_is_a_noop_that_returns_the_stored_one():
    stored = plan_node_write(None, SYSTEM, day(0)).node
    plan = plan_node_write(stored, SYSTEM, day(5))  # sent without valid_from, as a crawler would
    assert plan.action is WriteAction.NOOP and plan.node is stored


def test_a_changed_node_bumps_the_version_and_keeps_created_at_and_valid_from():
    stored = plan_node_write(None, SYSTEM, day(0)).node
    changed = SYSTEM.model_copy(update={"purpose": "Something else"})
    plan = plan_node_write(stored, changed, day(5))
    assert plan.action is WriteAction.UPDATE
    assert (plan.node.version, plan.node.created_at, plan.node.updated_at) == (2, day(0), day(5))
    assert plan.node.valid_from == day(0)


def test_evidence_is_immutable_but_resending_it_is_a_noop():
    stored = plan_node_write(None, evidence(), day(0)).node
    assert plan_node_write(stored, evidence(), day(5)).action is WriteAction.NOOP
    with pytest.raises(ImmutableNodeError):
        plan_node_write(stored, evidence().model_copy(update={"confidence": 0.5}), day(5))


def test_a_node_cannot_be_written_with_a_future_end():
    with pytest.raises(ValueError, match="future"):
        plan_node_write(
            None, SYSTEM.model_copy(update={"valid_from": day(0), "valid_to": day(1)}), day(0)
        )


# --- edges ----------------------------------------------------------------------------------


def test_a_new_edge_is_stamped_and_inserted():
    plan = plan_edge_write(None, owns(), day(0))
    assert plan.action is WriteAction.INSERT
    assert plan.edge.version == 1 and plan.edge.valid_from == day(0)


def test_an_unchanged_open_edge_is_a_noop():
    stored = stored_edge()
    plan = plan_edge_write(stored, owns(), day(5))
    assert plan.action is WriteAction.NOOP and plan.edge is stored


def test_a_changed_open_edge_bumps_the_version():
    stored = plan_edge_write(None, make_edge(EdgeType.MAPS_TO, "req:a:b", "ctl:VC-1"), day(0)).edge
    changed = make_edge(EdgeType.MAPS_TO, "req:a:b", "ctl:VC-1", rationale="Revised.")
    plan = plan_edge_write(stored, changed, day(5))
    assert plan.action is WriteAction.UPDATE and plan.edge.version == 2


def test_closing_keeps_the_first_valid_to_and_refuses_a_future_one():
    open_edge = stored_edge()
    closed = plan_close_edge(open_edge, day(2), day(2))
    assert closed.action is WriteAction.UPDATE
    assert (closed.edge.valid_to, closed.edge.version, closed.edge.updated_at) == (
        day(2),
        2,
        day(2),
    )
    again = plan_close_edge(closed.edge, day(4), day(4))
    assert again.action is WriteAction.NOOP and again.edge.valid_to == day(2)
    with pytest.raises(ValueError, match="future"):
        plan_close_edge(open_edge, day(3), day(2))
    with pytest.raises(ValueError, match="valid_to"):
        plan_close_edge(open_edge, day(-1), day(2))


def closed_edge():
    return plan_close_edge(stored_edge(), day(2), day(2)).edge


def test_an_open_edge_sent_for_a_closed_one_reopens_it():
    plan = plan_edge_write(closed_edge(), owns(), day(5))
    assert plan.action is WriteAction.UPDATE
    assert plan.edge.valid_from == day(5) and plan.edge.valid_to is None
    assert plan.edge.closed_intervals == ((day(0), day(2)),)
    assert plan.edge.version == 3


def test_a_stale_valid_from_on_reopen_starts_the_new_period_now():
    plan = plan_edge_write(closed_edge(), owns(valid_from=day(0)), day(5))
    assert plan.edge.valid_from == day(5)  # day(0) predates the close, so it is stale


def test_reopening_before_the_edge_closed_is_refused():
    with pytest.raises(ValueError, match="before it closed"):
        plan_edge_write(closed_edge(), owns(), day(1))  # a clock that went backwards


def test_the_same_closed_edge_sent_again_is_a_noop():
    historic = owns(valid_from=day(-9), valid_to=day(-1))
    stored = plan_edge_write(None, historic, day(0)).edge
    plan = plan_edge_write(stored, historic, day(5))
    assert plan.action is WriteAction.NOOP and plan.edge is stored


def test_a_correction_to_a_closed_edge_stays_closed():
    stored = plan_edge_write(None, owns(valid_from=day(-9), valid_to=day(-8)), day(0)).edge
    plan = plan_edge_write(stored, owns(valid_from=day(-9), valid_to=day(-7)), day(0))
    assert plan.action is WriteAction.UPDATE
    assert plan.edge.valid_to == day(-7) and plan.edge.closed_intervals == ()


def test_an_edge_cannot_be_written_with_a_future_end():
    with pytest.raises(ValueError, match="future"):
        plan_edge_write(None, owns(valid_from=day(0), valid_to=day(1)), day(0))


def test_edges_to_close_never_end_before_they_start():
    ended = SYSTEM.model_copy(update={"valid_from": day(0), "valid_to": day(2)})
    early, late = stored_edge(), plan_edge_write(None, owns(valid_from=day(3)), day(3)).edge
    assert edges_to_close(ended, [early, late]) == [(early, day(2)), (late, day(3))]


# --- usage ----------------------------------------------------------------------------------


def usage(**overrides):
    fields = {
        "tenant": COMMON["tenant"],
        "usage_id": uuid4(),
        "system_id": SYSTEM.id,
        "provider_id": "prov:mock-bedrock",
        "model_id": "model:fm-1",
        "timestamp": day(0),
        "token_estimate": 10,
        "source": Source.SIMULATED,
    } | overrides
    return UsageRecord(**fields)


def test_usage_identity_is_timestamp_and_usage_id():
    record = usage()
    assert usage_identity(record) == (day(0), str(record.usage_id))
    assert usage_identity(usage(usage_id=record.usage_id)) == usage_identity(record)
    assert usage_identity(usage()) != usage_identity(record)


def test_usage_bounds_must_be_aware():
    check_usage_bounds(None, None)
    check_usage_bounds(day(0), day(1))
    with pytest.raises(ValueError, match="timezone-aware"):
        check_usage_bounds(datetime(2026, 11, 5), None)


# --- purity ---------------------------------------------------------------------------------


def test_planning_reads_no_clock_and_touches_no_storage():
    source = Path(planning.__file__).read_text()
    for forbidden in ("datetime.now", "utcnow", "time.time", "boto3", "networkx", "import time"):
        assert forbidden not in source, forbidden
