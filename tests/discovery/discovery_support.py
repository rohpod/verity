"""Shared helpers for the discovery tests. Everything here is invented."""

import io
import json
import zipfile
from pathlib import Path

import boto3
from verity_core.discovery.aws import AwsClients, AwsCollector

ROOT = Path(__file__).parents[2]
CONTENT = ROOT / "content"
FIXTURE = CONTENT / "fixtures" / "crawl" / "estate.json"
CANARY = "VERITY-CANARY-7f3a"
REGION = "eu-north-1"
MOTO_ACCOUNT = "123456789012"

MANIFEST = "system: sys:talent-screening\nresources:\n  - {type: lambda, name: talent-screening}\n"

TRUST = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}


def fixture() -> dict:
    return json.loads(FIXTURE.read_text())


class StubCloudTrail:
    """moto 5.2.5 does not implement `LookupEvents`, so tests inject this instead."""

    def __init__(self, events=()):
        self.events = list(events)
        self.calls = []

    def get_paginator(self, operation):
        assert operation == "lookup_events"
        return self

    def paginate(self, **arguments):
        self.calls.append(arguments)
        wanted = arguments["LookupAttributes"][0]["AttributeValue"]
        yield {"Events": [e for e in self.events if e["EventSource"] == wanted]}


def trail_event(
    role: str, name: str = "Converse", source: str = "bedrock.amazonaws.com", when=None
):
    from datetime import UTC, datetime

    detail = {
        "userIdentity": {"sessionContext": {"sessionIssuer": {"userName": role}}},
        "requestParameters": {"messages": "a prompt that must never be kept"},
    }
    return {
        "EventSource": source,
        "EventName": name,
        "EventTime": when or datetime(2026, 11, 1, tzinfo=UTC),
        "CloudTrailEvent": json.dumps(detail),
    }


def zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("app.py", "def handler(event, context):\n    return {}\n")
    return buffer.getvalue()


def populate_moto(*, tags=None) -> None:
    """A function holding the canary, its role with an inline and a managed policy, a table and
    a manifest, inside an active `mock_aws()`."""
    iam = boto3.client("iam", region_name=REGION)
    iam.create_role(RoleName="shadow-role", AssumeRolePolicyDocument=json.dumps(TRUST))
    iam.put_role_policy(
        RoleName="shadow-role",
        PolicyName="models",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [{"Effect": "Allow", "Action": "bedrock:Converse", "Resource": "*"}],
            }
        ),
    )
    managed = iam.create_policy(
        PolicyName="read-table",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "dynamodb:GetItem",
                        "Resource": f"arn:aws:dynamodb:{REGION}:{MOTO_ACCOUNT}:table/verity-graph",
                    }
                ],
            }
        ),
    )["Policy"]["Arn"]
    iam.attach_role_policy(RoleName="shadow-role", PolicyArn=managed)
    lam = boto3.client("lambda", region_name=REGION)
    function = lam.create_function(
        FunctionName="shadow-summariser",
        Runtime="python3.12",
        Role=f"arn:aws:iam::{MOTO_ACCOUNT}:role/shadow-role",
        Handler="app.handler",
        Code={"ZipFile": zip_bytes()},
        Description="Summarises documents",
        Environment={"Variables": {"OPENAI_BASE_URL": CANARY, "LOG_LEVEL": CANARY}},
        Architectures=["arm64"],
        Tags=tags or {},
    )
    assert function["FunctionName"] == "shadow-summariser"
    boto3.client("dynamodb", region_name=REGION).create_table(
        TableName="verity-graph",
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    boto3.client("ssm", region_name=REGION).put_parameter(
        Name="/verity/manifests/talent.yaml",
        Type="String",
        Value=MANIFEST,
    )


def aws_collector(clock, *, trail=None, **kw) -> AwsCollector:
    clients = AwsClients(
        lambda_=boto3.client("lambda", region_name=REGION),
        tagging=boto3.client("resourcegroupstaggingapi", region_name=REGION),
        iam=boto3.client("iam", region_name=REGION),
        dynamodb=boto3.client("dynamodb", region_name=REGION),
        ssm=boto3.client("ssm", region_name=REGION),
        cloudtrail=trail if trail is not None else StubCloudTrail(),
    )
    return AwsCollector(
        clients,
        clock=clock,
        trail_event_sources=["bedrock.amazonaws.com"],
        trail_lookback_days=90,
        **kw,
    )
