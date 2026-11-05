from datetime import UTC, date, datetime, timedelta

import pytest
from rules_support import COMMON, date_of
from verity_core.model.edges import AppliesToEdge
from verity_core.model.enums import AppliesCondition, Role
from verity_core.rules.status import ApplicabilityStatus, applicability_status

NOON = timedelta(hours=12)


def edge(**fields) -> AppliesToEdge:
    return AppliesToEdge(
        src="req:euaia:art4",
        dst="org:kestrel",
        role=Role.PROVIDER,
        rule_id="eu-literacy",
        reason="Invented for the tests.",
        **COMMON,
        **fields,
    )


def at(day: date, delta: timedelta = timedelta()) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC) + delta


@pytest.mark.parametrize(
    "date_id",
    [
        "euaia-chapters-1-2",
        "euaia-general",
        "euaia-art50-2-legacy",
        "euaia-high-risk-annex-iii",
    ],
)
def test_each_obligation_date_is_upcoming_the_day_before_and_in_force_on_the_day(date_id):
    day = date_of(date_id)
    e = edge(in_force_from=day)
    assert applicability_status(e, at(day, -timedelta(seconds=1))) is ApplicabilityStatus.UPCOMING
    assert applicability_status(e, at(day - timedelta(days=1))) is ApplicabilityStatus.UPCOMING
    assert applicability_status(e, at(day)) is ApplicabilityStatus.IN_FORCE
    assert applicability_status(e, at(day, NOON)) is ApplicabilityStatus.IN_FORCE
    assert applicability_status(e, at(day + timedelta(days=400))) is ApplicabilityStatus.IN_FORCE


def test_no_date_means_in_force():
    assert applicability_status(edge(), at(date(2000, 1, 1))) is ApplicabilityStatus.IN_FORCE


def test_a_condition_wins_over_the_date_on_both_sides_of_it():
    e = edge(in_force_from=date(2027, 12, 2), condition=AppliesCondition.LEGACY_SIGNIFICANT_CHANGE)
    for when in (date(2027, 12, 1), date(2027, 12, 2), date(2030, 1, 1)):
        assert applicability_status(e, at(when)) is ApplicabilityStatus.CONDITIONAL


def test_a_conditional_edge_with_no_date_is_still_conditional():
    e = edge(condition=AppliesCondition.LEGACY_SIGNIFICANT_CHANGE)
    assert applicability_status(e, at(date(2026, 1, 1))) is ApplicabilityStatus.CONDITIONAL


def test_a_time_zone_is_read_as_utc():
    from datetime import timezone

    e = edge(in_force_from=date(2026, 8, 2))
    plus_two = timezone(timedelta(hours=2))
    # 2026-08-02 01:00 at +02:00 is still 2026-08-01 in UTC.
    assert (
        applicability_status(e, datetime(2026, 8, 2, 1, tzinfo=plus_two))
        is ApplicabilityStatus.UPCOMING
    )


def test_a_naive_as_of_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        applicability_status(edge(), datetime(2026, 1, 1))
