"""The OpenTofu estate equals `content/fixtures/crawl/estate.json`, so a live crawl classifies the
account the way `verity crawl --local` classifies the fixture (ADR 0025, decision 6). Also pins
the estate to the free allowance and to what must never be exposed."""

import json

import pytest
from estate_support import ROOT
from hcl_support import (
    ESTATE,
    INFRA,
    blocks,
    estate_locals,
    files,
    parse,
    resources,
    with_account,
)
from verity_core.graph.dynamodb import keys

LOCALS = estate_locals()
RESOURCES = resources()
FIXTURE = json.loads((ROOT / "content/fixtures/crawl/estate.json").read_text())
FUNCTIONS = {f["FunctionName"]: f for f in FIXTURE["functions"]}
ROLES = {r["role"]["RoleName"]: r for r in FIXTURE["roles"]}
TAGS = {
    m["ResourceARN"].rsplit(":", 1)[1]: {t["Key"]: t["Value"] for t in m["Tags"]}
    for m in FIXTURE["tag_mappings"]
}
IN_MODULE = {**LOCALS["apps"], **LOCALS["mocks"]}


def test_the_module_declares_exactly_the_fixtures_seven_functions():
    assert set(IN_MODULE) == set(FUNCTIONS)
    assert len(IN_MODULE) == 7


@pytest.mark.parametrize("name", sorted(FUNCTIONS))
def test_description_memory_timeout_runtime_and_architecture_match(name):
    fixture = FUNCTIONS[name]
    kind = "app" if name in LOCALS["apps"] else "mock"
    body = RESOURCES["aws_lambda_function"][kind]
    assert IN_MODULE[name]["description"] == fixture["Description"]
    assert IN_MODULE[name].get("memory_size", body["memory_size"]) == fixture["MemorySize"]
    assert body["timeout"] == fixture["Timeout"]
    assert body["runtime"] == fixture["Runtime"]
    assert body["architectures"] == fixture["Architectures"]
    assert body["handler"] == fixture["Handler"]


@pytest.mark.parametrize("name", sorted(FUNCTIONS))
def test_env_names_match_and_hold_no_canary(name):
    declared = set(FUNCTIONS[name].get("Environment", {}).get("Variables", {}))
    module = set(IN_MODULE[name].get("env", {}))
    if IN_MODULE[name].get("uses_openai"):
        module.add("OPENAI_BASE_URL")
    assert module == declared
    assert not [v for v in IN_MODULE[name].get("env", {}).values() if "CANARY" in v]


def test_env_values_are_the_ones_the_estate_notes_name():
    values = {n: a["env"] for n, a in LOCALS["apps"].items()}
    assert values["support-assistant"] == {
        "MODEL_ADAPTER": "mock-bedrock",
        "HELP_ARTICLES_FILE": "articles.json",
        "USAGE_TABLE": "verity-graph",
        "LOG_LEVEL": "INFO",
    }
    assert values["talent-screening"]["COEFFICIENTS_FILE"] == "coefficients.json"
    assert values["invoice-renderer"] == {"INVOICE_TEMPLATE": "template.txt"}
    assert values["contract-insights"]["USAGE_TABLE"] == "verity-graph"


@pytest.mark.parametrize("name", sorted(FUNCTIONS))
def test_tags_match_the_fixtures_tag_mappings(name):
    assert IN_MODULE[name]["tags"] == TAGS.get(name, {})


def test_shadow_summariser_and_talent_screening_have_no_tags():
    assert LOCALS["apps"]["shadow-summariser"]["tags"] == {}
    assert LOCALS["apps"]["talent-screening"]["tags"] == {}
    assert LOCALS["apps"]["invoice-renderer"]["tags"] == {}


def normal(statements):
    return sorted(
        ({**s, "Action": sorted(s["Action"]), "Resource": s["Resource"]} for s in statements),
        key=lambda s: json.dumps(s, sort_keys=True),
    )


@pytest.mark.parametrize("name", sorted(FUNCTIONS))
def test_the_role_policies_equal_the_fixtures(name):
    fixture = {
        p["PolicyName"]: normal(p["PolicyDocument"]["Statement"])
        for p in ROLES[f"{name}-role"]["inline_policies"]
    }
    module = {p: normal(s) for p, s in with_account(LOCALS["policies"][name]).items()}
    assert module == fixture
    assert ROLES[f"{name}-role"]["attached_policies"] == []


def test_the_trust_is_lambda_only_in_the_fixture_and_the_module():
    for role in ROLES.values():
        (statement,) = role["role"]["AssumeRolePolicyDocument"]["Statement"]
        assert statement["Principal"] == {"Service": "lambda.amazonaws.com"}
    body = RESOURCES["aws_iam_role"]["function"]
    assert body["assume_role_policy"].count("lambda.amazonaws.com") == 1


@pytest.mark.parametrize("name", ["support-assistant", "contract-insights"])
def test_leading_keys_names_only_the_systems_usage_partition(name):
    model = with_account(LOCALS["policies"][name]["model-and-data"])
    (put,) = [s for s in model if s["Action"] == ["dynamodb:PutItem"]]
    assert put["Condition"] == {
        "ForAllValues:StringEquals": {
            "dynamodb:LeadingKeys": [keys.usage_pk("kestrel", f"sys:{name}")]
        }
    }


@pytest.mark.parametrize("name", ["talent-screening", "shadow-summariser", "invoice-renderer"])
def test_an_app_that_writes_no_usage_has_no_table_access(name):
    text = json.dumps(LOCALS["policies"][name])
    assert "dynamodb" not in text


def test_support_assistant_keeps_the_seeded_bedrock_grant_that_the_boundary_neutralises():
    actions = {
        a for s in LOCALS["policies"]["support-assistant"]["model-and-data"] for a in s["Action"]
    }
    assert "bedrock:InvokeModel" in actions
    assert "bedrock:InvokeModel" not in {
        a
        for n in LOCALS["policies"]
        if n != "support-assistant"
        for p in LOCALS["policies"][n].values()
        for s in p
        for a in s["Action"]
    }


def test_every_role_including_the_schedulers_has_the_boundary():
    for kind, name in (("aws_iam_role", "function"), ("aws_iam_role", "scheduler")):
        assert RESOURCES[kind][name]["permissions_boundary"] == "${aws_iam_policy.boundary.arn}"
    assert len(RESOURCES["aws_iam_role"]) == 2


def test_the_estate_uses_the_alias_that_adds_no_tags_and_the_baseline_keeps_its_own():
    providers = [p["aws"] for p in parse(INFRA / "main.tf")["provider"]]
    (estate,) = [p for p in providers if p.get("alias") == "estate"]
    (baseline,) = [p for p in providers if "alias" not in p]
    assert "default_tags" not in estate
    assert baseline["default_tags"]
    for key in ("region", "allowed_account_ids"):
        assert estate[key] == baseline[key]
    assert blocks("module")["estate"]["providers"] == {"aws": "${aws.estate}"}
    assert blocks("module")["table"].get("providers") is None


def test_no_estate_resource_sets_tags_beyond_the_fixtures():
    tagged = {
        (kind, name)
        for kind, named in RESOURCES.items()
        for name, body in named.items()
        if "tags" in body or "tags_all" in body
    }
    assert {name for kind, name in tagged if kind == "aws_lambda_function"} == {
        "mock",
        "app",
        "crawler",
        "probe",
    }
    assert {k for k, _ in tagged} <= {
        "aws_lambda_function",
        "aws_dynamodb_table",
        "aws_budgets_budget",
    }


def test_nothing_exposes_an_arn_a_url_or_an_account_id():
    assert not [p for p in files(ESTATE) if "output" in parse(p)]
    for path in files(INFRA):
        for block in parse(path).get("output", []):
            for name, body in block.items():
                assert not any(w in str(body) for w in ("arn", "url", "account")), (path, name)


def test_every_parameter_is_standard_and_the_only_url_needs_iam():
    assert {b["tier"] for b in RESOURCES["aws_ssm_parameter"].values()} == {"Standard"}
    assert {b["authorization_type"] for b in RESOURCES["aws_lambda_function_url"].values()} == {
        "AWS_IAM"
    }


def test_only_the_approved_function_and_log_resources_are_counted_once_each():
    assert set(RESOURCES["aws_cloudwatch_log_group"]) == {"function"}
    assert set(RESOURCES["aws_lambda_function"]) == {"mock", "app", "crawler", "probe"}
    assert set(RESOURCES["aws_iam_policy"]) == {"boundary"}
