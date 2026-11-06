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


def trail_event_json(role: str, **kw) -> dict:
    """The same event with its time as text, for a fixture file."""
    return trail_event(role, **kw) | {"EventTime": "2026-11-01T00:00:00+00:00"}


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
                        "Resource": f"arn:aws:dynamodb:{REGION}:{MOTO_ACCOUNT}:table/app-table",
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
        TableName="app-table",
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


# --- clean records, built directly for the pure tests -------------------------------------

from verity_core.content.loader import load_content  # noqa: E402
from verity_core.discovery.boundary import (  # noqa: E402
    CollectedFunction,
    CollectedRole,
    Policy,
    Statement,
)

SIGNALS = load_content(CONTENT).signals


def make_function(name, env=(), description="", role=None) -> CollectedFunction:
    return CollectedFunction(
        name=name,
        arn=f"arn:aws:lambda:{REGION}:<account>:function:{name}",
        runtime="python3.12",
        handler="app.handler",
        role_arn=f"arn:aws:iam::<account>:role/{role or name + '-role'}",
        architectures=("arm64",),
        memory_mb=128,
        timeout_s=10,
        env_names=tuple(sorted(env)),
        code_sha256="x",
        description=description,
    )


def allow(actions, resources="*", effect="Allow", negated=False) -> Statement:
    actions = (actions,) if isinstance(actions, str) else tuple(sorted(actions))
    resources = (resources,) if isinstance(resources, str) else tuple(sorted(resources))
    return Statement(effect, actions, resources, negated)


def make_role(name, *statements) -> CollectedRole:
    return CollectedRole(
        name=name,
        arn=f"arn:aws:iam::<account>:role/{name}",
        trust=(),
        policies=(Policy("p", "inline", tuple(statements)),),
    )


# --- crawling ------------------------------------------------------------------------------

import dataclasses  # noqa: E402

from verity_core.content.seed import seed  # noqa: E402
from verity_core.discovery.collectors import FixtureCollector  # noqa: E402
from verity_core.discovery.pipeline import crawl  # noqa: E402
from verity_core.graph.dynamodb.table import TABLE_NAME  # noqa: E402
from verity_core.model.enums import EdgeType, NodeType  # noqa: E402
from verity_core.model.nodes import AISystem, Organisation  # noqa: E402

CONTENT_LOADED = load_content(CONTENT)
# Just the organisation and the three systems, so a test seeds in a moment on either backend.
MINI = dataclasses.replace(
    CONTENT_LOADED,
    estate=tuple(n for n in CONTENT_LOADED.estate if isinstance(n, Organisation | AISystem)),
    frameworks=(),
    requirements=(),
    controls=(),
    edges=(),
    decisions=(),
)


def seeded(repo, clock, content=MINI):
    seed(repo, content, clock)
    clock.advance(hours=1)
    return repo


def crawl_fixture(repo, clock, path=FIXTURE, content=MINI):
    return crawl(repo, content, FixtureCollector(path), clock)


def edited_fixture(tmp_path, edit) -> "Path":
    """A copy of the recorded estate after `edit(raw)`."""
    raw = fixture()
    edit(raw)
    path = tmp_path / f"estate-{len(list(tmp_path.iterdir()))}.json"
    path.write_text(json.dumps(raw))
    return path


def role_of(raw, function):
    return next(r for r in raw["roles"] if r["role"]["RoleName"] == f"{function}-role")


def dump(repo) -> str:
    """Every node, every version and every edge, as text, for a search."""
    parts = []
    for node_type in NodeType:
        for node in repo.nodes_by_type(node_type):
            parts.append(node.model_dump_json())
            parts += [v.model_dump_json() for v in repo.history(node.id)]
    graph = repo.load_graph()
    parts += [data["record"].model_dump_json() for _, _, data in graph.edges(data=True)]
    return "\n".join(parts)


def table_text(repo) -> str:
    """The whole DynamoDB table as text, or empty for the in-memory repository."""
    client = getattr(repo, "_client", None)
    if client is None:
        return ""
    found, token = [], {}
    while True:
        page = client.scan(TableName=TABLE_NAME, **token)
        found.append(json.dumps(page["Items"], default=str))
        if "LastEvaluatedKey" not in page:
            return "\n".join(found)
        token = {"ExclusiveStartKey": page["LastEvaluatedKey"]}


def open_edges(repo, edge_type: EdgeType) -> set[tuple[str, str]]:
    graph = repo.load_graph()
    return {
        (e.src, e.dst) for _, _, d in graph.edges(data=True) if (e := d["record"]).type is edge_type
    }


def of_type(repo, node_type: NodeType) -> list:
    return repo.nodes_by_type(node_type)
