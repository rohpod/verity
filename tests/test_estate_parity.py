"""The code and the crawl fixture describe the same estate, so M8's live crawl should match
`verity crawl --local` (ADR 0023). Env var names are read from each `app.py` by AST."""

import ast
import json

import pytest
from estate_support import ROOT
from verity_core.graph.dynamodb import keys

FUNCTIONS = {
    "support-assistant": "apps/support_assistant",
    "talent-screening": "apps/talent_screening",
    "contract-insights": "apps/contract_insights",
    "shadow-summariser": "apps/shadow_summariser",
    "invoice-renderer": "apps/invoice_renderer",
    "mock-bedrock": "mocks/mock_bedrock",
    "mock-openai": "mocks/mock_openai",
}
RESERVED = {"AWS_REGION"}  # set by Lambda, so the function may read it but never sets it
ESTATE = json.loads((ROOT / "content/fixtures/crawl/estate.json").read_text())
FIXTURE = {f["FunctionName"]: f for f in ESTATE["functions"]}


def env_names(relative: str) -> set[str]:
    """Names read as `os.environ[...]`, `os.environ.get(...)` or `os.getenv(...)`."""
    names = set()
    for node in ast.walk(ast.parse((ROOT / relative / "app.py").read_text())):
        key = None
        if isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
            key = node.slice
        elif isinstance(node, ast.Call) and ast.unparse(node.func) in {
            "os.environ.get",
            "os.getenv",
        }:
            key = node.args[0] if node.args else None
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            names.add(key.value)
    return names - RESERVED


@pytest.mark.parametrize(("function", "path"), FUNCTIONS.items())
def test_the_env_names_in_the_code_are_the_env_names_in_the_fixture(function, path):
    declared = set(FIXTURE[function].get("Environment", {}).get("Variables", {}))
    assert env_names(path) == declared


@pytest.mark.parametrize(("function", "path"), FUNCTIONS.items())
def test_the_handler_is_app_handler_and_exists(function, path):
    assert FIXTURE[function]["Handler"] == "app.handler"
    tree = ast.parse((ROOT / path / "app.py").read_text())
    assert any(isinstance(n, ast.FunctionDef) and n.name == "handler" for n in tree.body)


def test_all_seven_zip_names_are_fixture_functions():
    assert set(FUNCTIONS) <= set(FIXTURE)
    assert len(FUNCTIONS) == 7


def test_the_scan_finds_names_in_the_apps_that_read_them():
    assert env_names("apps/support_assistant") == {
        "MODEL_ADAPTER",
        "HELP_ARTICLES_FILE",
        "USAGE_TABLE",
        "LOG_LEVEL",
    }
    assert env_names("mocks/mock_openai") == set()


def test_no_fixture_name_remains_from_the_impossible_estate():
    names = {n for f in ESTATE["functions"] for n in f.get("Environment", {}).get("Variables", {})}
    assert not names & {"HELP_ARTICLES_TABLE", "TEMPLATE_BUCKET"}


def table_statements(role: dict) -> list[dict]:
    """`Allow` statements on the graph table. The crawler reads these, and M8 writes them."""
    return [
        statement
        for policy in role["inline_policies"]
        for statement in policy["PolicyDocument"]["Statement"]
        if "dynamodb" in str(statement["Action"]) and statement["Effect"] == "Allow"
    ]


ROLES = {r["role"]["RoleName"].removesuffix("-role"): r for r in ESTATE["roles"]}
USAGE_WRITERS = {"support-assistant", "contract-insights"}


@pytest.mark.parametrize("function", sorted(USAGE_WRITERS))
def test_an_app_role_may_only_put_into_the_usage_partition_the_code_writes(function):
    (statement,) = table_statements(ROLES[function])
    assert statement["Action"] == ["dynamodb:PutItem"]
    assert statement["Condition"] == {
        "ForAllValues:StringEquals": {
            "dynamodb:LeadingKeys": [keys.usage_pk("kestrel", f"sys:{function}")]
        }
    }


@pytest.mark.parametrize("function", ["talent-screening", "shadow-summariser"])
def test_an_app_that_writes_no_usage_has_no_table_access(function):
    assert table_statements(ROLES[function]) == []
