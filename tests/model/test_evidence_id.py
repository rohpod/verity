from datetime import UTC, datetime, timedelta, timezone

import pytest
from verity_core.model.evidence import content_sha256, evidence_id
from verity_core.model.hashing import canonical_json

T0 = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
SUBJECT = "res:lambda:eu-north-1:support-assistant"
COLLECTOR = "crawler@0.1.0"


def make(subject=SUBJECT, collector=COLLECTOR, at=T0, content=None):
    return evidence_id(subject, collector, at, content_sha256(content or {"runtime": "python3.12"}))


def test_canonical_json_ignores_key_order_and_whitespace():
    assert canonical_json({"b": 1, "a": [1, 2]}) == canonical_json({"a": [1, 2], "b": 1})
    assert canonical_json({"a": 1}) == '{"a":1}'


def test_canonical_json_rejects_nan():
    with pytest.raises(ValueError):
        canonical_json({"a": float("nan")})


def test_same_inputs_give_the_same_id():
    assert make() == make()
    assert make().startswith("ev:") and len(make()) == len("ev:") + 32


def test_recollecting_identical_content_later_gives_a_new_id_and_the_same_sha256():
    later = T0 + timedelta(days=1)
    assert make(at=later) != make()
    assert content_sha256({"runtime": "python3.12"}) == content_sha256({"runtime": "python3.12"})


def test_id_changes_with_each_hashed_field():
    base = make()
    assert make(subject="res:lambda:eu-north-1:other") != base
    assert make(collector="cli@0.1.0") != base
    assert make(content={"runtime": "python3.13"}) != base


def test_content_key_order_does_not_change_the_id():
    assert make(content={"a": 1, "b": 2}) == make(content={"b": 2, "a": 1})


def test_same_instant_in_another_timezone_gives_the_same_id():
    plus_two = timezone(timedelta(hours=2))
    assert make(at=T0.astimezone(plus_two)) == make()


def test_field_boundaries_are_unambiguous():
    h = content_sha256({})
    assert evidence_id("a", "bc", T0, h) != evidence_id("ab", "c", T0, h)


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        evidence_id(SUBJECT, COLLECTOR, datetime(2026, 11, 5), content_sha256({}))


def test_content_hash_ignores_stamped_fields_only():
    from factories import evidence
    from verity_core.model.hashing import content_hash

    e = evidence()
    stamped = e.model_copy(update={"version": 3, "created_at": T0, "updated_at": T0})
    assert content_hash(stamped) == content_hash(e)
    assert content_hash(e.model_copy(update={"confidence": 0.5})) != content_hash(e)
