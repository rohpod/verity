"""`infra/` must match `table_definition()` and stay free. CI runs this without credentials, so
a change that would cost money fails before anyone can apply it (CLAUDE.md, ADR 0015)."""

import re
from pathlib import Path

import hcl2
import pytest
from verity_core.graph.dynamodb.table import FREE_ALLOWANCE_UNITS, table_definition

INFRA = Path(__file__).parents[2] / "infra"
# M8 adds to this, with verified prices. Anything else needs its own approval first.
APPROVED_RESOURCES = {"aws_budgets_budget", "aws_dynamodb_table"}
PAID_TABLE_SETTINGS = {
    "point_in_time_recovery",
    "replica",
    "stream_enabled",
    "ttl",
    "global_table_witness",
}


def clean(value):
    """python-hcl2 keeps the quotes of string literals in some versions."""
    if isinstance(value, str):
        return value.strip('"')
    if isinstance(value, dict):
        return {clean(k): clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def parse(path: Path) -> dict:
    with path.open() as file:
        return clean(hcl2.load(file))


def resources() -> dict[str, dict]:
    found = {}
    for path in sorted(INFRA.rglob("*.tf")):
        if ".terraform" in path.parts:
            continue
        for block in parse(path).get("resource", []):
            for kind, named in block.items():
                found.setdefault(kind, {}).update(named)
    return found


def only(kind: str) -> dict:
    ((body,),) = [list(resources()[kind].values())]
    return body


@pytest.fixture
def table():
    return only("aws_dynamodb_table")


def test_only_approved_resource_types_exist():
    assert set(resources()) <= APPROVED_RESOURCES


def test_the_table_matches_its_single_description(table):
    wanted = table_definition()
    assert table["name"] == wanted["TableName"]
    assert table["billing_mode"] == wanted["BillingMode"] == "PROVISIONED"
    assert table["table_class"] == wanted["TableClass"] == "STANDARD"
    assert {a["name"]: a["type"] for a in table["attribute"]} == {
        a["AttributeName"]: a["AttributeType"] for a in wanted["AttributeDefinitions"]
    }
    assert [table["hash_key"], table["range_key"]] == [
        k["AttributeName"] for k in wanted["KeySchema"]
    ]
    assert table["read_capacity"] == wanted["ProvisionedThroughput"]["ReadCapacityUnits"]
    assert table["write_capacity"] == wanted["ProvisionedThroughput"]["WriteCapacityUnits"]


def test_the_index_matches_its_single_description(table):
    (index,) = table["global_secondary_index"]
    (wanted,) = table_definition()["GlobalSecondaryIndexes"]
    assert index["name"] == wanted["IndexName"]
    assert index["projection_type"] == wanted["Projection"]["ProjectionType"]
    assert [(k["attribute_name"], k["key_type"]) for k in index["key_schema"]] == [
        (k["AttributeName"], k["KeyType"]) for k in wanted["KeySchema"]
    ]
    assert index["read_capacity"] == wanted["ProvisionedThroughput"]["ReadCapacityUnits"]
    assert index["write_capacity"] == wanted["ProvisionedThroughput"]["WriteCapacityUnits"]


def test_capacity_stays_inside_the_always_free_allowance(table):
    (index,) = table["global_secondary_index"]
    assert table["read_capacity"] + index["read_capacity"] <= FREE_ALLOWANCE_UNITS
    assert table["write_capacity"] + index["write_capacity"] <= FREE_ALLOWANCE_UNITS


def test_the_table_has_no_setting_that_could_cost_money(table):
    assert not PAID_TABLE_SETTINGS & set(table)


def test_the_budget_excludes_credits_and_has_no_actions():
    budget = only("aws_budgets_budget")
    (cost_types,) = budget["cost_types"]
    assert cost_types["include_credit"] is False
    assert (budget["budget_type"], budget["limit_amount"]) == ("COST", "0.01")
    assert {n["notification_type"] for n in budget["notification"]} == {"ACTUAL", "FORECASTED"}


def test_no_real_account_id_or_email_is_committed():
    for path in INFRA.rglob("*"):
        if not path.is_file() or any(p.startswith(".terraform") for p in path.parts):
            continue
        if path.name in ("terraform.tfvars", "terraform.tfstate", "terraform.tfstate.backup"):
            continue  # git-ignored, and they hold the real values on purpose
        text = path.read_text()
        assert set(re.findall(r"\b\d{12}\b", text)) <= {"000000000000"}, path
        assert set(re.findall(r"@[\w.-]+\.\w+", text)) <= {"@example.invalid"}, path
