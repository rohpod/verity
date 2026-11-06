import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).parent.parent / ".claude" / "hooks" / "confirm-mutating-aws.py"
spec = importlib.util.spec_from_file_location("confirm_mutating_aws", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

MUST_ASK = [
    "tofu apply",
    "tofu apply -auto-approve",
    "terraform destroy",
    "tofu -chdir=infra apply",
    "cd infra && tofu apply",
    "AWS_PROFILE=x tofu apply",
    "/opt/homebrew/bin/tofu destroy",
    "tofu state rm aws_dynamodb_table.graph",
    "tofu import aws_dynamodb_table.graph verity-graph",
    "bash -c 'tofu apply'",
    "aws dynamodb create-table --table-name x",
    "aws lambda delete-function --function-name x",
    "aws ssm put-parameter --name x --value y",
    "aws --region eu-north-1 lambda update-function-code --function-name x",
    "aws iam attach-role-policy --role-name r --policy-arn p",
    "aws lambda invoke --function-name x out.json",
    "aws login",
    "echo hi | aws s3 cp - s3://b/k",
    "tofu apply 'unterminated",
    "aws ce get-cost-and-usage --time-period x",
    "aws --region us-east-1 ce get-cost-forecast",
    "VERITY_LIVE_AWS=1 uv run pytest tests/live",
    "env VERITY_LIVE_AWS=1 uv run pytest tests/live",
    "export VERITY_LIVE_AWS=1 && uv run pytest tests/live",
    "bash -c 'VERITY_LIVE_AWS=1 uv run pytest'",
    "uv run verity seed --target dynamodb",
    "uv run verity seed --target=dynamodb --yes",
    "verity seed --content content --target dynamodb",
    "cd /repo && uv run verity seed --tenant kestrel --target dynamodb",
    "bash -c 'uv run verity seed --target dynamodb'",
    "uv run python -m verity_core.cli seed --target dynamodb",
    "uv run verity assess --target dynamodb",
    "uv run verity assess --target=dynamodb --yes",
    "uv run verity assess --as-of 2026-11-05 --system sys:x --target dynamodb",
    "cd /repo && uv run verity assess --tenant kestrel --target dynamodb",
    "bash -c 'uv run verity assess --target dynamodb'",
    "uv run python -m verity_core.cli assess --target dynamodb",
    "uv run verity crawl",
    "uv run verity crawl --verbose",
    "verity crawl --content content",
    "cd /repo && uv run verity crawl",
    "bash -c 'uv run verity crawl'",
    "uv run python -m verity_core.cli crawl",
]

MUST_PASS = [
    "tofu plan",
    "uv run pytest tests/graph",
    "tofu validate",
    "tofu fmt -check",
    "tofu init",
    "tofu state list",
    "terraform output",
    "aws sts get-caller-identity",
    "aws lambda list-functions --region eu-north-1",
    "aws dynamodb describe-table --table-name x",
    "aws --profile p --region eu-north-1 lambda get-account-settings",
    "aws cloudtrail lookup-events",
    "aws configure get region",
    "aws --version",
    "grep apply docs/architecture.md",
    "echo 'tofu apply is mutating'",
    "uv run pytest",
    "git status",
    "uv run verity lint",
    "uv run verity seed",
    "uv run verity seed --target memory",
    "uv run verity assess",
    "uv run verity assess --target memory --as-of 2026-12-02",
    "uv run verity attest VC-001 org:kestrel --by person:l-ivanova",
    "echo 'verity assess --target dynamodb'",
    "grep -rn 'assess --target dynamodb' docs",
    "uv run verity seed --content tests/content --target memory",
    "echo 'verity seed --target dynamodb'",
    "grep -rn 'seed --target dynamodb' docs",
    "uv run verity crawl --local",
    "uv run verity crawl --local --verbose",
    "uv run verity crawl --help",
    "echo 'verity crawl'",
    "grep -rn 'verity crawl' docs",
]


@pytest.mark.parametrize("command", MUST_ASK)
def test_asks_for_confirmation(command):
    assert hook.reason_for(command), command


@pytest.mark.parametrize("command", MUST_PASS)
def test_allows_read_only(command):
    assert hook.reason_for(command) is None, command


def run_hook(stdin: str) -> str:
    return subprocess.run(
        [sys.executable, str(HOOK)], input=stdin, capture_output=True, text=True, check=True
    ).stdout


def test_hook_emits_ask_decision_for_tofu_apply():
    out = json.loads(run_hook(json.dumps({"tool_input": {"command": "tofu apply"}})))
    decision = out["hookSpecificOutput"]
    assert decision["permissionDecision"] == "ask"
    assert "tofu apply" in decision["permissionDecisionReason"]


def test_hook_is_silent_for_safe_command():
    assert run_hook(json.dumps({"tool_input": {"command": "tofu plan"}})) == ""


def test_hook_asks_when_input_is_garbage():
    out = json.loads(run_hook("not json"))
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"
