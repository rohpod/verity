"""The estate's functions, Function URL, manifests and schedule, read from the OpenTofu files
(ADR 0025, decisions 6 and 8). Nothing is applied and nothing reaches AWS."""

import ast

from estate_support import ROOT
from hcl_support import ESTATE, blocks, estate_locals, resources

LOCALS = estate_locals()
RESOURCES = resources()
FUNCTION_KINDS = ("mock", "app", "crawler", "probe")
FORBIDDEN_FUNCTION_SETTINGS = {
    "reserved_concurrent_executions",
    "tracing_config",
    "vpc_config",
    "layers",
    "dead_letter_config",
    "publish",
    "snap_start",
    "ephemeral_storage",
    "file_system_config",
}


def function(kind: str) -> dict:
    return RESOURCES["aws_lambda_function"][kind]


def env_read_by(relative: str) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse((ROOT / relative).read_text())):
        if isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
            names.add(node.slice.value)
    return names


def test_every_function_is_python_3_12_on_arm64_with_the_app_handler_from_the_build_dir():
    for kind in FUNCTION_KINDS:
        body = function(kind)
        assert body["runtime"] == "python3.12", kind
        assert body["architectures"] == ["arm64"], kind
        assert body["handler"] == "app.handler", kind
        assert body["filename"].startswith("${var.build_dir}/"), kind
        assert body["filename"].endswith(".zip"), kind
        assert body["source_code_hash"].startswith("${try(filebase64sha256("), kind
        assert body["source_code_hash"].endswith(', "")}'), kind


def test_memory_and_timeout_are_the_fixtures_for_the_estate_and_the_adrs_for_the_crawler():
    for kind in ("mock", "app", "probe"):
        assert (function(kind)["memory_size"], function(kind)["timeout"]) == (128, 10), kind
    assert (function("crawler")["memory_size"], function("crawler")["timeout"]) == (256, 300)


def test_no_function_uses_a_setting_the_estate_does_not_need():
    for kind in FUNCTION_KINDS:
        assert not FORBIDDEN_FUNCTION_SETTINGS & set(function(kind)), kind
    assert "aws_lambda_alias" not in RESOURCES
    assert "aws_lambda_layer_version" not in RESOURCES
    assert "aws_lambda_provisioned_concurrency_config" not in RESOURCES


def test_the_crawler_env_names_are_the_ones_its_handler_reads():
    (env,) = function("crawler")["environment"]
    assert set(env["variables"]) == env_read_by("crawler/handler.py")
    assert env["variables"]["TENANT"] == "kestrel"
    assert env["variables"]["SIGNALS_FILE"] == "rules/ai_signals.yaml"


def test_the_probe_env_names_are_the_ones_its_handler_reads():
    (env,) = function("probe")["environment"]
    assert set(env["variables"]) == env_read_by("crawler/probe.py")


def test_the_crawler_is_tagged_as_a_platform_component_and_has_no_retries():
    assert function("crawler")["tags"] == {"verity:component": "verity-crawler"}
    config = RESOURCES["aws_lambda_function_event_invoke_config"]["crawler"]
    assert config["maximum_retry_attempts"] == 0
    assert config["function_name"] == "${aws_lambda_function.crawler.function_name}"


def test_the_only_function_url_is_mock_openai_and_needs_iam():
    (name,) = RESOURCES["aws_lambda_function_url"]
    body = RESOURCES["aws_lambda_function_url"][name]
    assert body["authorization_type"] == "AWS_IAM"
    assert body["function_name"] == '${aws_lambda_function.mock["mock-openai"].function_name}'
    assert "aws_lambda_permission" not in RESOURCES  # no resource policy: callers need IAM


def test_the_openai_base_url_is_the_function_url_plus_v1():
    expected = '${trimsuffix(aws_lambda_function_url.mock_openai.function_url, "/")}/v1'
    assert LOCALS["openai_base_url"].replace("\\", "") == expected
    body = function("app")
    (env,) = body["dynamic"][0]["environment"]["content"]
    assert "OPENAI_BASE_URL" in env["variables"].replace("\\", "")
    assert "local.openai_base_url" in env["variables"]
    assert {n for n, a in LOCALS["apps"].items() if a["uses_openai"]} == {
        "contract-insights",
        "shadow-summariser",
    }


def test_the_schedule_starts_disabled_at_0300_utc_with_no_retries():
    body = RESOURCES["aws_scheduler_schedule"]["crawl"]
    assert body["state"] == "${var.schedule_state}"
    assert body["schedule_expression"] == "cron(0 3 * * ? *)"
    assert body["schedule_expression_timezone"] == "UTC"
    assert body["flexible_time_window"] == [{"mode": "OFF"}]
    (target,) = body["target"]
    assert target["retry_policy"] == [{"maximum_retry_attempts": 0}]
    assert target["arn"] == "${aws_lambda_function.crawler.arn}"


def test_the_schedule_and_the_probe_default_to_off_at_both_levels():
    for where in (ESTATE, ESTATE.parents[2]):
        variables = blocks("variable", where)
        assert variables["schedule_state"]["default"] == "DISABLED"
        assert variables["enable_probe"]["default"] is False


def test_the_probe_exists_only_while_enabled_and_runs_on_the_support_assistant_role():
    body = function("probe")
    assert body["count"] == "${var.enable_probe ? 1 : 0}"
    assert body["role"] == '${aws_iam_role.function["support-assistant"].arn}'


def test_the_scheduler_may_invoke_the_crawler_and_nothing_else():
    policy = RESOURCES["aws_iam_role_policy"]["scheduler"]["policy"].replace("\\", "")
    assert 'Action = ["lambda:InvokeFunction"]' in policy
    assert "Resource = aws_lambda_function.crawler.arn" in policy
    assert policy.count("Action") == 1
    assert "scheduler.amazonaws.com" in RESOURCES["aws_iam_role"]["scheduler"]["assume_role_policy"]


def test_the_manifests_are_standard_tier_parameters_named_after_the_files():
    body = RESOURCES["aws_ssm_parameter"]["manifest"]
    assert body["tier"] == "Standard"
    assert body["type"] == "String"
    assert body["name"] == "/verity/manifests/${each.key}"
    assert body["for_each"] == '${fileset(var.manifests_dir, "*.yaml")}'
    assert body["value"] == '${file("${var.manifests_dir}/${each.key}")}'


def test_the_root_passes_the_repository_paths_and_the_estate_provider():
    module = blocks("module")["estate"]
    assert module["build_dir"] == "${path.root}/../.build"
    assert module["manifests_dir"] == "${path.root}/../content/manifests"
    assert module["providers"] == {"aws": "${aws.estate}"}
