"""Usage records in DynamoDB (D7, D8, ADR 0013)."""

from datetime import timedelta, timezone
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from conftest import START
from dynamo_support import SpyClient, repo_for, rows
from factories import COMMON
from verity_core.graph.dynamodb import keys
from verity_core.graph.dynamodb.table import TABLE_NAME
from verity_core.graph.dynamodb.usage import DynamoDBUsageSink
from verity_core.graph.errors import TenantMismatchError
from verity_core.graph.repository import GraphRepository, UsageSink
from verity_core.model.enums import Source
from verity_core.model.usage import UsageRecord

SYSTEM = "sys:support-assistant"


def usage(minutes=0, **overrides):
    fields = {
        "tenant": COMMON["tenant"],
        "usage_id": uuid4(),
        "system_id": SYSTEM,
        "provider_id": "prov:mock-bedrock",
        "model_id": "model:fm-1",
        "timestamp": START + timedelta(minutes=minutes),
        "token_estimate": 120,
        "source": Source.SIMULATED,
    } | overrides
    return UsageRecord(**fields)


class OnlyPut:
    """A client that may only call `put_item`, like an app role limited to `dynamodb:PutItem`."""

    def __init__(self, inner):
        self._inner = inner
        self.puts = 0

    def put_item(self, **kwargs):
        self.puts += 1
        return self._inner.put_item(**kwargs)

    def __getattr__(self, name):
        raise AssertionError(f"the usage sink called {name}, which an app role may not")


def test_the_sink_works_with_a_client_that_can_only_put(table):
    sink = DynamoDBUsageSink("kestrel", client=OnlyPut(table.client))
    record = usage()
    sink.append_usage(record)
    assert rows(table) == [
        (keys.usage_pk("kestrel", SYSTEM), keys.usage_sk(START, record.usage_id))
    ]


def test_the_sink_is_the_narrow_interface_and_not_a_repository(table):
    sink = DynamoDBUsageSink("kestrel", client=table.client)
    assert isinstance(sink, UsageSink) and not isinstance(sink, GraphRepository)


def test_a_usage_item_lives_in_its_own_usage_partition_with_no_graph_keys(table):
    record = usage()
    DynamoDBUsageSink("kestrel", client=table.client).append_usage(record)
    (item,) = table.client.scan(TableName=TABLE_NAME)["Items"]
    assert (
        item["PK"]["S"] == keys.usage_pk("kestrel", SYSTEM) == "T#kestrel#U#sys:support-assistant"
    )
    assert item["SK"]["S"].startswith("U#2026-11-05T09:00:00.000000Z#")
    assert {"ver", "GSI1PK", "GSI1SK"}.isdisjoint(item)


def test_the_repository_delegates_and_makes_one_call(table):
    spy = SpyClient(table.client)
    repo_for(table, client=spy).append_usage(usage())
    assert dict(spy.calls) == {"put_item": 1}


def test_a_retried_write_is_left_alone_and_the_first_one_wins(table):
    spy = SpyClient(table.client)
    repo = repo_for(table, client=spy)
    first = usage(token_estimate=10)
    repo.append_usage(first)
    stored = table.client.scan(TableName=TABLE_NAME)["Items"]
    repo.append_usage(first.model_copy(update={"token_estimate": 999}))  # the same usage_id
    assert table.client.scan(TableName=TABLE_NAME)["Items"] == stored
    assert spy.calls["put_item"] == 2 and repo.usage_records(SYSTEM) == [first]


def test_other_aws_errors_are_not_swallowed(table):
    sink = DynamoDBUsageSink("kestrel", client=table.client, table_name="no-such-table")
    with pytest.raises(ClientError) as caught:
        sink.append_usage(usage())
    assert caught.value.response["Error"]["Code"] == "ResourceNotFoundException"


def test_the_sink_refuses_another_tenants_record(table):
    sink = DynamoDBUsageSink("kestrel", client=table.client)
    with pytest.raises(TenantMismatchError):
        sink.append_usage(usage(tenant="other"))
    assert rows(table) == []


def test_the_same_instant_in_another_timezone_is_the_same_record(table):
    repo = repo_for(table)
    record = usage()
    repo.append_usage(record)
    elsewhere = record.model_copy(
        update={"timestamp": START.astimezone(timezone(timedelta(hours=2)))}
    )
    repo.append_usage(elsewhere)
    assert len(rows(table)) == 1


def test_two_tenants_keep_their_usage_apart(table):
    repo_for(table, "kestrel").append_usage(usage())
    repo_for(table, "other").append_usage(usage(tenant="other"))
    assert [r.tenant for r in repo_for(table, "kestrel").usage_records(SYSTEM)] == ["kestrel"]
    assert [r.tenant for r in repo_for(table, "other").usage_records(SYSTEM)] == ["other"]


# --- reading ---------------------------------------------------------------------------------


def test_an_empty_or_backwards_interval_returns_nothing_without_asking_dynamodb(table):
    spy = SpyClient(table.client)
    repo = repo_for(table, client=spy)
    repo.append_usage(usage(5))
    at = START + timedelta(minutes=5)
    assert repo.usage_records(SYSTEM, since=at, until=at) == []
    assert repo.usage_records(SYSTEM, since=at, until=at - timedelta(minutes=1)) == []
    assert spy.calls["query"] == 0  # DynamoDB would reject a BETWEEN that runs backwards


def test_usage_comes_back_oldest_first_across_pages(table):
    class TwoPerPage(SpyClient):
        def query(self, **kwargs):
            return self._inner.query(Limit=2, **kwargs)

    repo = repo_for(table)
    records = [usage(minutes) for minutes in (30, 0, 20, 10, 50, 40, 60)]
    for record in records:
        repo.append_usage(record)
    paged = repo_for(table, client=TwoPerPage(table.client)).usage_records(SYSTEM)
    assert [r.timestamp for r in paged] == sorted(r.timestamp for r in records)


def test_the_interval_is_half_open_in_dynamodb(table):
    repo = repo_for(table)
    records = [usage(m) for m in (0, 10, 20)]
    for record in records:
        repo.append_usage(record)
    since, until = START + timedelta(minutes=10), START + timedelta(minutes=20)
    assert repo.usage_records(SYSTEM, since=since, until=until) == [records[1]]
    assert repo.usage_records(SYSTEM, since=since) == records[1:]
    assert repo.usage_records(SYSTEM, until=until) == records[:2]


def test_usage_never_turns_up_in_a_node_listing_or_the_graph(table):
    repo = repo_for(table)
    repo.append_usage(usage())
    assert repo.load_graph().number_of_nodes() == 0


def test_writing_usage_leaves_the_systems_node_partition_without_a_usage_item(table):
    repo = repo_for(table)
    repo.append_usage(usage())
    node_partition = keys.node_pk("kestrel", SYSTEM)
    assert not [sk for pk, sk in rows(table) if pk == node_partition]
    found = table.client.query(
        TableName=TABLE_NAME,
        KeyConditionExpression="PK = :pk",
        ExpressionAttributeValues={":pk": {"S": node_partition}},
    )
    assert found["Count"] == 0
