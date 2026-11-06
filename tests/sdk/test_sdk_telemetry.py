"""`UsageRecorder` writing through both usage sinks (D8, ADR 0013, ADR 0023)."""

from datetime import timedelta

import boto3
import pytest
from factories import TENANT
from moto import mock_aws
from verity_ai.bedrock import BedrockCompatible
from verity_ai.telemetry import UsageRecorder
from verity_core.graph.dynamodb.repository import DynamoDBRepository
from verity_core.graph.dynamodb.table import table_definition
from verity_core.graph.dynamodb.usage import DynamoDBUsageSink
from verity_core.graph.memory import InMemoryRepository
from verity_core.model import ids
from verity_core.model.enums import Source

SYSTEM = ids.system_id("support-assistant")
CONVERSE = {"usage": {"totalTokens": 11}}


def recorder(sink, clock):
    return UsageRecorder(
        sink,
        tenant=TENANT,
        system_id=SYSTEM,
        provider_id=ids.provider_id("mock-bedrock"),
        model_id=ids.model_id("bedrock-fm"),
        clock=clock,
    )


def test_a_call_writes_one_simulated_record_to_the_memory_repository(clock):
    repo = InMemoryRepository(TENANT, clock)
    BedrockCompatible(lambda r: CONVERSE, usage=recorder(repo, clock)).converse(
        modelId="m", messages=[]
    )
    [record] = repo.usage_records(SYSTEM)
    assert record.source is Source.SIMULATED
    assert record.token_estimate == 11
    assert (record.provider_id, record.model_id) == ("prov:mock-bedrock", "model:bedrock-fm")
    assert record.timestamp == clock.now


def test_the_dynamodb_sink_writes_a_record_the_repository_reads_back(clock):
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        sink = DynamoDBUsageSink(TENANT, client=client)
        hook = recorder(sink, clock)
        hook(5)
        clock.now += timedelta(seconds=1)
        hook(6)
        repo = DynamoDBRepository(TENANT, clock, client=client)
        assert [r.token_estimate for r in repo.usage_records(SYSTEM)] == [5, 6]


def test_every_call_gets_a_fresh_usage_id(clock):
    repo = InMemoryRepository(TENANT, clock)
    hook = recorder(repo, clock)
    hook(1)
    hook(1)
    assert len(repo.usage_records(SYSTEM)) == 2


def test_a_sink_that_raises_does_not_fail_the_call(clock):
    class Broken:
        def append_usage(self, record):
            raise RuntimeError("table unavailable")

    adapter = BedrockCompatible(lambda r: CONVERSE, usage=recorder(Broken(), clock))
    assert adapter.converse(modelId="m", messages=[]) == CONVERSE


def test_a_bad_token_count_is_refused_by_the_record(clock):
    with pytest.raises(ValueError):
        recorder(InMemoryRepository(TENANT, clock), clock)(-1)
