from datetime import UTC, datetime, timedelta

import pytest
from rules_support import COMMON
from verity_core.model.enums import EvidenceKind
from verity_core.model.evidence import Evidence
from verity_core.rules.decisions import superseded_decision_ids

DAY = datetime(2026, 11, 5, tzinfo=UTC)


def decision(name, *, supersedes=(), collected_at=DAY, valid_for=timedelta(days=365)):
    extra = {"supersedes": list(supersedes)} if supersedes else {}
    return Evidence.build(
        subject="sys:s",
        collector="person:l-ivanova",
        collected_at=collected_at,
        valid_until=collected_at + valid_for,
        kind=EvidenceKind.ATTESTATION,
        content={"decision_id": name, "decision_kind": "verification", **extra},
        **COMMON,
    )


def test_a_decision_is_superseded_from_the_moment_the_new_one_is_collected():
    new = decision("new", supersedes=["old"])
    assert superseded_decision_ids([new], DAY - timedelta(seconds=1)) == frozenset()
    assert superseded_decision_ids([new], DAY) == {"old"}


def test_supersession_survives_the_expiry_of_the_superseding_decision():
    new = decision("new", supersedes=["old"], valid_for=timedelta(days=1))
    assert superseded_decision_ids([new], DAY + timedelta(days=400)) == {"old"}


def test_decisions_that_supersede_nothing_add_nothing():
    assert superseded_decision_ids([decision("a"), decision("b")], DAY) == frozenset()


def test_a_naive_as_of_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        superseded_decision_ids([], datetime(2026, 11, 5))
