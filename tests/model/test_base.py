from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from verity_core.model.base import Envelope
from verity_core.model.enums import Source


def envelope(**overrides):
    fields = {"tenant": "kestrel", "source": Source.SYNTHETIC} | overrides
    return Envelope(**fields)


def test_defaults_mean_not_yet_stored():
    e = envelope()
    assert e.version == 0
    assert e.created_at is None and e.valid_from is None and e.valid_to is None
    assert e.confidence == 1.0


def test_records_are_frozen_and_strict():
    e = envelope()
    with pytest.raises(ValidationError):
        e.tenant = "other"
    with pytest.raises(ValidationError):
        Envelope(tenant="kestrel", source=Source.SYNTHETIC, email="a@example.com")


def test_datetimes_normalise_to_utc():
    local = datetime(2026, 11, 5, 11, 0, tzinfo=timezone(timedelta(hours=2)))
    assert envelope(valid_from=local).valid_from == datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
    assert envelope(valid_from=local).valid_from.utcoffset() == timedelta(0)


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValidationError):
        envelope(valid_from=datetime(2026, 11, 5))


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_is_a_probability(confidence):
    with pytest.raises(ValidationError):
        envelope(confidence=confidence)


def test_tenant_and_source_are_required_and_validated():
    with pytest.raises(ValidationError):
        envelope(tenant="")
    with pytest.raises(ValidationError):
        envelope(source="made-up")
