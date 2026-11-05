from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from verity_core.model.enums import Source
from verity_core.model.usage import UsageRecord

FIELDS = {
    "tenant": "kestrel",
    "usage_id": uuid4(),
    "system_id": "sys:support-assistant",
    "provider_id": "prov:mock-bedrock",
    "model_id": "model:fm-1",
    "timestamp": datetime(2026, 11, 5, 9, 0, tzinfo=UTC),
    "token_estimate": 120,
    "source": Source.SIMULATED,
}


def test_valid_record_round_trips_through_json():
    record = UsageRecord(**FIELDS)
    assert UsageRecord.model_validate(record.model_dump(mode="json")) == record


def test_records_are_frozen_and_strict():
    record = UsageRecord(**FIELDS)
    with pytest.raises(ValidationError):
        record.token_estimate = 1
    with pytest.raises(ValidationError):
        UsageRecord(**FIELDS, prompt="never store prompt text")


@pytest.mark.parametrize(
    "field,value",
    [
        ("system_id", "prov:x"),
        ("provider_id", "sys:x"),
        ("model_id", "prov:x"),
        ("usage_id", "not-a-uuid"),
        ("token_estimate", -1),
        ("timestamp", datetime(2026, 11, 5)),
        ("tenant", ""),
    ],
)
def test_invalid_fields_are_rejected(field, value):
    with pytest.raises(ValidationError):
        UsageRecord(**FIELDS | {field: value})


def test_timestamp_is_normalised_to_utc():
    local = datetime(2026, 11, 5, 11, 0, tzinfo=timezone(timedelta(hours=2)))
    assert UsageRecord(**FIELDS | {"timestamp": local}).timestamp == FIELDS["timestamp"]
