import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import boto3
from discovery_support import (
    CANARY,
    FIXTURE,
    MOTO_ACCOUNT,
    REGION,
    StubCloudTrail,
    aws_collector,
    fixture,
    populate_moto,
    trail_event,
)
from moto import mock_aws
from verity_core.discovery.aws import AwsClients, AwsCollector
from verity_core.discovery.collectors import Collector, FixtureCollector
from verity_core.model.enums import Source

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)

# The operations the collector may call, as `<boto3 service>:<operation>`. `tag:` in IAM is the
# `resourcegroupstaggingapi` client in boto3.
ALLOWED_OPERATIONS = {
    "lambda:ListFunctions",
    "resourcegroupstaggingapi:GetResources",
    "iam:ListRoles",
    "iam:ListRolePolicies",
    "iam:GetRolePolicy",
    "iam:ListAttachedRolePolicies",
    "iam:GetPolicy",
    "iam:GetPolicyVersion",
    "dynamodb:ListTables",
    "ssm:GetParametersByPath",
    "cloudtrail:LookupEvents",
}


def test_the_fixture_collector_reads_the_recorded_estate_and_says_it_is_simulated():
    collector = FixtureCollector(FIXTURE)
    assert collector.source is Source.SIMULATED
    found = collector.collect()
    assert [f.name for f in found.functions] == [f["FunctionName"] for f in fixture()["functions"]]
    assert {t.name for t in found.tables} == {"verity-graph"}
    assert [m.system for m in found.manifests] == ["sys:talent-screening", "sys:contract-insights"]
    assert found.manifests_invalid == 0
    assert found.trail_events == ()
    assert len(found.roles) == 7


def test_the_fixture_collector_drops_every_env_value_and_account_id():
    found = FixtureCollector(FIXTURE).collect()
    assert CANARY not in repr(found)
    assert "000000000000" not in repr(found)


def test_an_invalid_manifest_in_the_fixture_is_counted_not_fatal(tmp_path):
    raw = fixture()
    raw["manifests"].append({"Name": "/verity/manifests/bad.yaml", "Value": "system: [oops"})
    path = tmp_path / "estate.json"
    path.write_text(json.dumps(raw))
    found = FixtureCollector(path).collect()
    assert found.manifests_invalid == 1
    assert len(found.manifests) == 2


def test_both_collectors_satisfy_the_protocol():
    assert isinstance(FixtureCollector(FIXTURE), Collector)
    assert isinstance(AwsCollector.__new__(AwsCollector), Collector)


def test_the_aws_collector_says_it_is_discovered():
    assert AwsCollector.source is Source.DISCOVERED


def test_the_aws_collector_reads_a_moto_account_and_drops_values_and_account_ids():
    with mock_aws():
        populate_moto(tags={"ai:system-id": "sys:x"})
        found = aws_collector(lambda: NOW).collect()
    function = found.functions[0]
    assert function.name == "shadow-summariser"
    assert function.env_names == ("LOG_LEVEL", "OPENAI_BASE_URL")
    assert function.architectures == ("arm64",)
    assert {r.name for r in found.roles} == {"shadow-role"}
    role = found.roles[0]
    assert {p.kind for p in role.policies} == {"inline", "managed"}
    assert [t.name for t in found.tables] == ["app-table"]
    assert [m.system for m in found.manifests] == ["sys:talent-screening"]
    assert found.tags_by_arn == {function.arn: {"ai:system-id": "sys:x"}}
    assert CANARY not in repr(found)
    assert MOTO_ACCOUNT not in repr(found)


def test_get_function_is_never_called_and_every_operation_is_expected():
    seen = []
    with mock_aws():
        populate_moto()
        collector = aws_collector(lambda: NOW)
        for client in (
            collector.clients.lambda_,
            collector.clients.tagging,
            collector.clients.iam,
            collector.clients.dynamodb,
            collector.clients.ssm,
        ):
            client.meta.events.register(
                "before-call",
                lambda model, **_: seen.append(f"{model.service_model.service_name}:{model.name}"),
            )
        collector.collect()
    assert seen
    assert set(seen) <= ALLOWED_OPERATIONS
    assert not any("GetFunction" in operation or "Invoke" in operation for operation in seen)


def test_cloudtrail_is_asked_for_each_configured_source_over_the_lookback():
    trail = StubCloudTrail([trail_event("r"), trail_event("r", source="other.amazonaws.com")])
    with mock_aws():
        populate_moto()
        found = aws_collector(lambda: NOW, trail=trail).collect()
    assert [e.event_source for e in found.trail_events] == ["bedrock.amazonaws.com"]
    (call,) = trail.calls
    assert call["LookupAttributes"] == [
        {"AttributeKey": "EventSource", "AttributeValue": "bedrock.amazonaws.com"}
    ]
    assert call["EndTime"] == NOW
    assert (call["EndTime"] - call["StartTime"]).days == 90


def test_service_linked_roles_are_not_part_of_the_estate():
    with mock_aws():
        iam = boto3.client("iam", region_name=REGION)
        trust = json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "x.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            }
        )
        iam.create_role(RoleName="svc", Path="/aws-service-role/x/", AssumeRolePolicyDocument=trust)
        iam.create_role(RoleName="mine", AssumeRolePolicyDocument=trust)
        found = aws_collector(lambda: NOW).collect()
    assert [r.name for r in found.roles] == ["mine"]


def test_a_raw_function_that_fails_validation_leaks_nothing(capsys, caplog):
    class BadLambda:
        def get_paginator(self, operation):
            return self

        def paginate(self):
            yield {
                "Functions": [{"FunctionName": "f", "Environment": {"Variables": {"K": CANARY}}}]
            }

    class Empty:
        def get_paginator(self, operation):
            return self

        def paginate(self, **_):
            return iter(())

    clients = AwsClients(
        lambda_=BadLambda(),
        tagging=Empty(),
        iam=Empty(),
        dynamodb=Empty(),
        ssm=Empty(),
        cloudtrail=StubCloudTrail(),
    )
    collector = AwsCollector(
        clients, clock=lambda: NOW, trail_event_sources=[], trail_lookback_days=90
    )
    try:
        collector.collect()
    except Exception as exc:  # noqa: BLE001
        import traceback

        text = "".join(traceback.format_exception(exc))
    else:
        raise AssertionError("expected a failure")
    out = capsys.readouterr()
    assert CANARY not in text + out.out + out.err + caplog.text
    assert "malformed function record" in text


def test_discovery_never_names_an_operation_that_reads_code_or_runs_it():
    """Only `invoke_crawler` may invoke, and only the crawler (ADR 0025, decision 2). The
    collector, which runs with the crawler's own role, never does."""
    forbidden = {"get_function", "get_function_configuration", "invoke", "Invoke"}
    package = Path(__file__).parents[2] / "core" / "verity_core" / "discovery"
    found = []
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text())
        allowed = {
            id(inner)
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "invoke_crawler"
            for inner in ast.walk(node)
        }
        for node in ast.walk(tree):
            if id(node) in allowed:
                continue
            names = []
            if isinstance(node, ast.Attribute):
                names.append(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.append(node.value)
            found += [(path.name, n) for n in names if n in forbidden]
    assert found == []
