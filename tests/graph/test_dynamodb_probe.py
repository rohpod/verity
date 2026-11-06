"""The refused-write probe (ADR 0025, decision 5), against moto and a stub. No AWS call."""

import importlib.util
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from verity_core.graph.dynamodb import keys
from verity_core.graph.dynamodb.probe import ALLOWED, NEVER_TRUE, attempt_refused_writes
from verity_core.graph.dynamodb.table import TABLE_NAME, table_definition

ROOT = Path(__file__).resolve().parents[2]
SYSTEM, OTHER = "sys:support-assistant", "sys:contract-insights"


def put(client, pk, sk, **extra):
    client.put_item(
        TableName=TABLE_NAME, Item={"PK": {"S": pk}, "SK": {"S": sk}, "doc": {"S": "x"}, **extra}
    )


def everything(client):
    return client.scan(TableName=TABLE_NAME)["Items"]


def test_with_the_items_present_nothing_changes_and_the_condition_is_what_refuses():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        put(client, keys.node_pk("kestrel", SYSTEM), keys.META)
        put(client, keys.usage_pk("kestrel", OTHER), "U#probe")
        before = everything(client)
        outcome = attempt_refused_writes(client, TABLE_NAME, "kestrel", SYSTEM, OTHER)
        assert everything(client) == before
    assert outcome == {
        "own_meta": "ConditionalCheckFailedException",
        "other_usage": "ConditionalCheckFailedException",
    }


def test_with_no_item_present_nothing_is_created_either():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        attempt_refused_writes(client, TABLE_NAME, "kestrel", SYSTEM, OTHER)
        assert everything(client) == []


def test_the_condition_cannot_be_true():
    assert "attribute_exists(PK)" in NEVER_TRUE and "attribute_not_exists(PK)" in NEVER_TRUE


class Refusing:
    def __init__(self, code):
        self.code, self.calls = code, []

    def put_item(self, **arguments):
        self.calls.append(arguments)
        raise ClientError(
            {"Error": {"Code": self.code, "Message": "User: arn:aws:iam::1:role/x is not ..."}},
            "PutItem",
        )


def test_an_access_denied_is_returned_as_its_code_and_nothing_else():
    stub = Refusing("AccessDeniedException")
    outcome = attempt_refused_writes(stub, "t", "kestrel", SYSTEM, OTHER)
    assert outcome == {"own_meta": "AccessDeniedException", "other_usage": "AccessDeniedException"}
    assert "arn:" not in str(outcome)


def test_the_two_targets_are_outside_the_systems_own_usage_partition():
    stub = Refusing("AccessDeniedException")
    attempt_refused_writes(stub, "t", "kestrel", SYSTEM, OTHER)
    own = keys.usage_pk("kestrel", SYSTEM)
    targets = [(c["Item"]["PK"]["S"], c["Item"]["SK"]["S"]) for c in stub.calls]
    assert targets == [
        (keys.node_pk("kestrel", SYSTEM), "META"),
        (keys.usage_pk("kestrel", OTHER), "U#probe"),
    ]
    assert own not in {pk for pk, _ in targets}
    assert all(c["ConditionExpression"] == NEVER_TRUE for c in stub.calls)


def test_a_write_dynamodb_accepts_is_reported_as_allowed():
    class Accepting:
        def put_item(self, **arguments):
            return {}

    assert attempt_refused_writes(Accepting(), "t", "kestrel", SYSTEM, OTHER) == {
        "own_meta": ALLOWED,
        "other_usage": ALLOWED,
    }


@pytest.fixture
def probe_module():
    spec = importlib.util.spec_from_file_location("crawler_probe", ROOT / "crawler/probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_handler_probes_the_table_it_is_given(probe_module, monkeypatch):
    monkeypatch.setenv("GRAPH_TABLE", "somewhere")
    stub = Refusing("AccessDeniedException")
    monkeypatch.setattr(probe_module, "usage_client", lambda: stub)
    assert probe_module.handler({}, None) == {
        "own_meta": "AccessDeniedException",
        "other_usage": "AccessDeniedException",
    }
    assert {c["TableName"] for c in stub.calls} == {"somewhere"}
