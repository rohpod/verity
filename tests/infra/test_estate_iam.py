"""The estate's roles, boundary and log groups, read from the OpenTofu files (ADR 0025,
decisions 6 and 7). Nothing is applied and nothing reaches AWS."""

import json
import re

from estate_support import ROOT
from hcl_support import ESTATE, estate_locals, resources, with_account

LOCALS = estate_locals()
NEVER_USE = json.loads((ROOT / "infra/bootstrap/verity-never-use.json").read_text())
FIXTURE = json.loads((ROOT / "content/fixtures/crawl/estate.json").read_text())
EXPECTED_ROLES = {
    "support-assistant",
    "talent-screening",
    "contract-insights",
    "shadow-summariser",
    "invoice-renderer",
    "mock-openai",
    "mock-bedrock",
    "verity-crawler",
}


def all_statements(function: str) -> list[dict]:
    return [s for named in [LOCALS["policies"][function]] for p in named.values() for s in p]


def test_the_boundary_denies_exactly_the_bedrock_and_sagemaker_entries_of_verity_never_use():
    (denied,) = [s["Action"] for s in NEVER_USE["Statement"] if s["Effect"] == "Deny"]
    models = sorted(a for a in denied if a.startswith(("bedrock:", "sagemaker:")))
    assert sorted(LOCALS["boundary_deny"]) == models
    # bedrock:Converse* stays for safety even though it matches no action (ADR 0025, decision 7)
    assert "bedrock:Converse*" in LOCALS["boundary_deny"]


def test_the_boundary_policy_allows_all_and_denies_the_list():
    body = resources()["aws_iam_policy"]["boundary"]
    assert body["name"] == "verity-function-boundary"
    policy = body["policy"]
    assert "local.boundary_deny" in policy
    assert 'Effect = "Allow", Action = "*", Resource = "*"' in policy.replace('\\"', '"')
    assert 'Effect = "Deny", Action = local.boundary_deny' in policy.replace('\\"', '"')


def test_every_function_role_has_the_boundary_and_trusts_only_lambda():
    body = resources()["aws_iam_role"]["function"]
    assert body["permissions_boundary"] == "${aws_iam_policy.boundary.arn}"
    assert body["name"] == "${each.key}-role"
    assert "lambda.amazonaws.com" in body["assume_role_policy"]
    assert "sts:AssumeRole" in body["assume_role_policy"]
    assert body["assume_role_policy"].count("Service") == 1


def test_there_is_a_role_for_each_function_and_none_for_the_probe():
    expected = '${toset(concat(keys(local.apps), keys(local.mocks), ["verity-crawler"]))}'
    assert resources()["aws_iam_role"]["function"]["for_each"] == "${local.role_names}"
    assert LOCALS["role_names"].replace("\\", "") == expected
    assert set(LOCALS["apps"]) | set(LOCALS["mocks"]) | {"verity-crawler"} == EXPECTED_ROLES
    assert set(LOCALS["policies"]) == EXPECTED_ROLES


def test_every_log_group_has_3_day_retention_and_a_role_has_no_create_log_group():
    group = resources()["aws_cloudwatch_log_group"]["function"]
    assert group["retention_in_days"] == 3
    assert group["name"] == "/aws/lambda/${each.key}"
    assert group["for_each"] == "${local.role_names}"
    for function in EXPECTED_ROLES:
        actions = {a for s in all_statements(function) for a in s["Action"]}
        assert "logs:CreateLogGroup" not in actions, function


def test_each_log_policy_reaches_only_its_own_group():
    for function in EXPECTED_ROLES:
        (logs,) = LOCALS["policies"][function]["logs"]
        assert logs["Action"] == ["logs:CreateLogStream", "logs:PutLogEvents"]
        assert logs["Resource"] == (
            f"arn:aws:logs:eu-north-1:${{var.account_id}}:log-group:/aws/lambda/{function}:*"
        )


def test_no_account_id_is_written_out_in_the_module():
    for path in ESTATE.glob("*.tf"):
        found = set(re.findall(r"\b\d{12}\b", path.read_text()))
        assert found <= {"000000000000"}, path
    assert with_account("${var.account_id}") == "000000000000"
