"""Account IDs become digests (ADR 0022, decision 4): different accounts stay different, and no
name stops a run."""

import json

from discovery_support import (
    FIXTURE,
    crawl_fixture,
    dump,
    edited_fixture,
    of_type,
    open_edges,
    role_of,
    seeded,
    table_text,
)
from verity_core.discovery.names import function_id, table_id
from verity_core.model.enums import EdgeType, NodeType

RAW_ACCOUNTS = ("111122223333", "444455556666", "000000000000", "123456789012")


def trust_naming(account):
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": f"arn:aws:iam::{account}:root"},
                "Action": "sts:AssumeRole",
            }
        ],
    }


def with_trust(account):
    def edit(raw):
        role_of(raw, "invoice-renderer")["role"]["AssumeRolePolicyDocument"] = trust_naming(account)

    return edit


def test_swapping_the_external_account_in_a_trust_policy_is_a_change(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock, edited_fixture(tmp_path, with_trust("111122223333")))
    clock.advance(hours=1)
    same = crawl_fixture(repo, clock, edited_fixture(tmp_path, with_trust("111122223333")))
    assert same.changes == ()
    clock.advance(hours=1)
    swapped = crawl_fixture(repo, clock, edited_fixture(tmp_path, with_trust("444455556666")))
    assert [c.rpartition(":")[2] for c in swapped.changes] == ["invoice-renderer-role"]
    assert len(of_type(repo, NodeType.CHANGE_EVENT)) == 1


def test_numbers_in_names_do_not_stop_the_run_and_stay_distinct(repo, clock, tmp_path):
    seeded(repo, clock)

    def numbered(raw):
        template = next(f for f in raw["functions"] if f["FunctionName"] == "invoice-renderer")
        for name in ("report-123456789012", "job-202611060900", "job-202611060901"):
            raw["functions"].append(template | {"FunctionName": name, "Role": template["Role"]})
            raw["functions"][-1]["FunctionArn"] = template["FunctionArn"].replace(
                "invoice-renderer", name
            )
        template["Environment"]["Variables"]["KEY_123456789012"] = "x"

    report = crawl_fixture(repo, clock, edited_fixture(tmp_path, numbered))
    assert len(report.functions) == 9
    names = {r.name for r in of_type(repo, NodeType.AWS_RESOURCE) if r.resource_type == "lambda"}
    assert sum(n.startswith("job-acct_") for n in names) == 2
    assert not any("123456789012" in n or "2026110609" in n for n in names)
    renderer = next(r for r in of_type(repo, NodeType.AWS_RESOURCE) if r.name == "invoice-renderer")
    assert any(n.startswith("KEY_acct_") for n in renderer.env_var_names)


def test_a_role_name_holding_the_account_crawls_and_the_number_is_nowhere(repo, clock, tmp_path):
    seeded(repo, clock)

    def cdk(raw):
        found = role_of(raw, "invoice-renderer")
        found["role"]["RoleName"] = "MyStack-Role-123456789012"
        found["role"]["Arn"] = found["role"]["Arn"].replace(
            "invoice-renderer-role", "MyStack-Role-123456789012"
        )
        next(f for f in raw["functions"] if f["FunctionName"] == "invoice-renderer")["Role"] = (
            found["role"]["Arn"]
        )
        raw["functions"][4]["Description"] = "Account 123456789012 owns this"

    crawl_fixture(repo, clock, edited_fixture(tmp_path, cdk))
    everything = dump(repo) + table_text(repo)
    for raw_number in RAW_ACCOUNTS:
        assert raw_number not in everything
    assert (function_id("invoice-renderer"), "x") not in open_edges(repo, EdgeType.ASSUMES)
    assert any(
        d.startswith("res:iam-role:global:MyStack-Role-acct_")
        for _, d in open_edges(repo, EdgeType.ASSUMES)
    )


def test_a_table_arn_still_gives_calls_from_a_named_and_a_wildcard_policy(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    wanted = (function_id("support-assistant"), table_id("verity-graph"))
    assert wanted in open_edges(repo, EdgeType.CALLS)

    def wildcard(raw):
        statement = {
            "Effect": "Allow",
            "Action": "dynamodb:GetItem",
            "Resource": "arn:aws:dynamodb:*:*:table/verity-*",
        }
        role_of(raw, "invoice-renderer")["inline_policies"].append(
            {"PolicyName": "w", "PolicyDocument": {"Statement": [statement]}}
        )

    clock.advance(hours=1)
    crawl_fixture(repo, clock, edited_fixture(tmp_path, wildcard))
    assert (function_id("invoice-renderer"), table_id("verity-graph")) in open_edges(
        repo, EdgeType.CALLS
    )


def test_the_recorded_fixture_account_is_not_in_anything_written(repo, clock):
    assert "000000000000" in FIXTURE.read_text()
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    assert "000000000000" not in dump(repo) + table_text(repo)
    assert json.loads(FIXTURE.read_text())["tables"] == ["verity-graph"]
