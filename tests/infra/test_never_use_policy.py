"""The explicit denies on the admin user (ADR 0015). The hard constraints in CLAUDE.md are
enforced by AWS as well as by review. An admin could remove this policy, so it stops accidents,
not intent."""

import json
from pathlib import Path

POLICY = Path(__file__).parents[2] / "infra" / "bootstrap" / "verity-never-use.json"
INLINE_USER_POLICY_LIMIT = 2048  # characters, not counting whitespace

REQUIRED = {
    "apigateway:*",
    "bedrock:Converse*",
    "bedrock:Invoke*",
    "cloudtrail:CreateEventDataStore",
    "cloudtrail:CreateTrail",
    "config:*",
    "ec2:CreateFlowLogs",
    "ec2:CreateNatGateway",
    "freetier:UpgradeAccountPlan",
    "neptune-graph:*",
    "organizations:CreateAccount",
    "organizations:CreateOrganization",
    "rds:CreateDBCluster",
    "rds:CreateDBInstance",
    "s3:CreateBucket",
    "sagemaker:InvokeEndpoint*",
    "secretsmanager:*",
}


def statements() -> list[dict]:
    return json.loads(POLICY.read_text())["Statement"]


def test_every_statement_denies_and_nothing_is_allowed():
    assert statements()
    assert {s["Effect"] for s in statements()} == {"Deny"}
    assert all(s["Resource"] == "*" for s in statements())


def test_every_never_use_action_is_denied():
    assert {action for s in statements() for action in s["Action"]} >= REQUIRED


def test_the_policy_never_blocks_what_verity_needs():
    denied = {action for s in statements() for action in s["Action"]}
    assert not {a for a in denied if a.split(":")[0] in ("dynamodb", "lambda", "budgets", "iam")}


def test_it_fits_as_an_inline_user_policy():
    assert len("".join(POLICY.read_text().split())) <= INLINE_USER_POLICY_LIMIT
