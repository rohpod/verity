"""The crawler's role grants what the crawler calls and nothing else (ADR 0025, decision 6).

The discovery actions are derived by recording the collector's clients against moto. The table
actions are derived from the repository's own source and from a recorded crawl, so a new call
there fails this test instead of failing in the account."""

import ast
import re

import boto3
from discovery_support import (
    MINI,
    ROOT,
    aws_collector,
    populate_moto,
    seeded,
)
from hcl_support import estate_locals
from moto import mock_aws
from verity_core.discovery.aws import AwsClients, AwsCollector
from verity_core.discovery.pipeline import crawl
from verity_core.graph.dynamodb.repository import DynamoDBRepository
from verity_core.graph.dynamodb.table import table_definition

ROLE = estate_locals()["policies"]["verity-crawler"]
DYNAMODB_SOURCES = ("repository.py", "usage.py")
PREFIX = {"lambda_": "lambda", "tagging": "tag"}


def camel(operation: str) -> str:
    return "".join(part.capitalize() for part in operation.split("_"))


class Recording:
    """Wraps a client and records each operation used, directly or through a paginator."""

    def __init__(self, inner, service, seen):
        self._inner, self._service, self._seen = inner, service, seen

    def get_paginator(self, operation):
        self._seen.add(f"{self._service}:{camel(operation)}")
        return self._inner.get_paginator(operation)

    def __getattr__(self, name):
        attribute = getattr(self._inner, name)
        if callable(attribute):

            def call(*args, **kwargs):
                self._seen.add(f"{self._service}:{camel(name)}")
                return attribute(*args, **kwargs)

            return call
        return attribute


def granted(policy_name: str) -> set[str]:
    return {a for s in ROLE[policy_name] for a in s["Action"]}


def test_the_discovery_actions_are_exactly_the_operations_the_collector_calls(clock):
    seen: set[str] = set()
    with mock_aws():
        populate_moto(tags={"ai:system-id": "sys:lead-scoring"})
        real = aws_collector(clock)
        clients = AwsClients(
            **{
                name: Recording(getattr(real.clients, name), PREFIX.get(name, name), seen)
                for name in ("lambda_", "tagging", "iam", "dynamodb", "ssm", "cloudtrail")
            }
        )
        AwsCollector(
            clients,
            clock=clock,
            trail_event_sources=["bedrock.amazonaws.com"],
            trail_lookback_days=90,
        ).collect()
    discovery = granted("discovery")
    assert seen == discovery
    assert "lambda:GetFunction" not in discovery
    assert not [a for a in discovery if "*" in a]


def test_each_discovery_statement_that_can_be_scoped_is():
    ssm = [s for s in ROLE["discovery"] if s["Action"] == ["ssm:GetParametersByPath"]]
    assert [s["Resource"] for s in ssm] == [
        "arn:aws:ssm:eu-north-1:${var.account_id}:parameter/verity/manifests*"
    ]


def repository_operations() -> set[str]:
    """`self._client.<operation>(` in the repository and the usage sink."""
    found = set()
    package = ROOT / "core/verity_core/graph/dynamodb"
    for name in DYNAMODB_SOURCES:
        for node in ast.walk(ast.parse((package / name).read_text())):
            if isinstance(node, ast.Call) and ast.unparse(node.func).startswith("self._client."):
                found.add(node.func.attr)
    return found


def test_the_graph_actions_are_what_the_repository_calls():
    actions = {
        "get_item": "GetItem",
        "batch_get_item": "BatchGetItem",
        "put_item": "PutItem",
        "query": "Query",
        "scan": "Scan",
        "transact_write_items": "PutItem",  # IAM authorises each Put in it as PutItem
    }
    operations = repository_operations()
    assert operations <= set(actions)
    assert granted("graph") == {f"dynamodb:{actions[o]}" for o in operations}


def test_the_transactions_only_ever_put():
    source = (ROOT / "core/verity_core/graph/dynamodb/repository.py").read_text()
    kinds = set(re.findall(r'\{"(Put|Update|Delete|ConditionCheck)":', source))
    assert kinds == {"Put"}


class SpyDynamo:
    def __init__(self, inner, seen):
        self._inner, self._seen = inner, seen

    def __getattr__(self, name):
        attribute = getattr(self._inner, name)
        if not callable(attribute):
            return attribute

        def call(*args, **kwargs):
            self._seen.add(name)
            return attribute(*args, **kwargs)

        return call


def test_a_recorded_seed_and_crawl_uses_only_granted_operations(clock):
    seen: set[str] = set()
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        repo = DynamoDBRepository("kestrel", clock, client=SpyDynamo(client, seen))
        populate_moto(tags={"ai:system-id": "sys:lead-scoring"})
        seeded(repo, clock)
        crawl(repo, MINI, aws_collector(clock), clock)
    assert seen and seen <= repository_operations()


def test_the_graph_statement_reaches_only_the_graph_table_and_its_index():
    (statement,) = ROLE["graph"]
    assert statement["Resource"] == [
        "arn:aws:dynamodb:eu-north-1:${var.account_id}:table/verity-graph",
        "arn:aws:dynamodb:eu-north-1:${var.account_id}:table/verity-graph/index/GSI1",
    ]
    assert not [
        a
        for a in statement["Action"]
        if a.endswith(("*", "Table", "Item"))
        and a not in {"dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:BatchGetItem"}
    ]


def test_the_crawler_role_names_no_other_action():
    every = {a for s in sum(ROLE.values(), []) for a in s["Action"]}
    assert not [a for a in every if a.startswith(("dynamodb:*", "iam:*", "lambda:*"))]
    assert every.isdisjoint({"lambda:GetFunction", "lambda:InvokeFunction", "s3:GetObject"})
