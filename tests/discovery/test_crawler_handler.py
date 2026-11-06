"""The deployed crawler's handler and the `verity crawl` command that invokes it (ADR 0025).

The handler runs against moto, with CloudTrail stubbed because moto 5.2.5 has no `LookupEvents`.
The invoke runs against a stub Lambda client. Nothing here reaches AWS."""

import importlib.util
import io
import json

import boto3
import pytest
from discovery_support import (
    CANARY,
    CONTENT,
    MOTO_ACCOUNT,
    REGION,
    ROOT,
    StubCloudTrail,
    populate_moto,
)
from moto import mock_aws
from verity_core import cli
from verity_core.discovery import aws
from verity_core.discovery.aws import AwsClients, CrawlerFailed, invoke_crawler
from verity_core.graph.dynamodb.table import TABLE_NAME, table_definition

SIGNALS = "rules/ai_signals.yaml"


def load_handler():
    spec = importlib.util.spec_from_file_location("crawler_handler", ROOT / "crawler/handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def crawler_env(monkeypatch):
    monkeypatch.setenv("GRAPH_TABLE", TABLE_NAME)
    monkeypatch.setenv("TENANT", "kestrel")
    monkeypatch.setenv("SIGNALS_FILE", str(CONTENT / SIGNALS))


@pytest.fixture
def handler_module(monkeypatch, crawler_env):
    """The handler, with moto clients and a stub for CloudTrail."""
    module = load_handler()

    def create(region=REGION):
        return AwsClients(
            lambda_=boto3.client("lambda", region_name=region),
            tagging=boto3.client("resourcegroupstaggingapi", region_name=region),
            iam=boto3.client("iam", region_name=region),
            dynamodb=boto3.client("dynamodb", region_name=region),
            ssm=boto3.client("ssm", region_name=region),
            cloudtrail=StubCloudTrail(),
        )

    monkeypatch.setattr(module.AwsClients, "create", staticmethod(create))
    return module


def test_the_handler_crawls_the_account_and_writes_the_graph(handler_module):
    with mock_aws():
        boto3.client("dynamodb", region_name=REGION).create_table(**table_definition())
        populate_moto(tags={"ai:system-id": "sys:lead-scoring"})
        result = handler_module.handler({}, None)
        again = handler_module.handler({}, None)
    assert result["functions"] == 1
    assert result["candidates"] == 1
    assert result["likelihood"] == {"declared": 1}
    assert result["written"]["runs"] == 1 and sum(result["written"].values()) > 1
    assert result["summary"]["largest_evidence_bytes"] > 0
    assert again["written"] == {"runs": 1}  # a second crawl writes only the run (ADR 0021)


def test_the_handler_returns_counts_only(handler_module):
    with mock_aws():
        boto3.client("dynamodb", region_name=REGION).create_table(**table_definition())
        populate_moto(tags={"ai:system-id": "sys:lead-scoring"})
        result = handler_module.handler({}, None)
    text = json.dumps(result)
    for forbidden in (
        "shadow-summariser",
        "shadow-role",
        "arn:",
        MOTO_ACCOUNT,
        CANARY,
        "app-table",
    ):
        assert forbidden not in text
    assert json.loads(text) == result  # JSON, as Lambda returns it


def test_the_handler_reads_its_settings_from_the_environment(handler_module, monkeypatch):
    monkeypatch.delenv("GRAPH_TABLE")
    with mock_aws(), pytest.raises(KeyError):
        handler_module.handler({}, None)


def test_the_handler_does_not_log_the_canary(handler_module, caplog):
    caplog.set_level("DEBUG")
    with mock_aws():
        boto3.client("dynamodb", region_name=REGION).create_table(**table_definition())
        populate_moto()
        handler_module.handler({}, None)
    assert CANARY not in caplog.text


# --- invoke_crawler -----------------------------------------------------------------------


class StubLambda:
    def __init__(self, payload=None, error=None):
        self.payload = json.dumps(payload or {"functions": 2}).encode()
        self.error = error
        self.calls = []

    def invoke(self, **arguments):
        self.calls.append(arguments)
        response = {"Payload": io.BytesIO(self.payload), "StatusCode": 200}
        if self.error:
            response["FunctionError"] = self.error
        return response


def test_invoke_runs_the_crawler_function_once_and_waits_for_it():
    client = StubLambda({"functions": 7})
    assert invoke_crawler(client) == {"functions": 7}
    assert client.calls == [{"FunctionName": "verity-crawler", "InvocationType": "RequestResponse"}]


def test_a_function_error_raises_without_the_payload():
    client = StubLambda({"errorMessage": CANARY, "errorType": "KeyError"}, error="Unhandled")
    with pytest.raises(CrawlerFailed) as caught:
        invoke_crawler(client)
    assert CANARY not in str(caught.value) and "Unhandled" not in str(caught.value)


def test_the_client_waits_longer_than_the_function_and_never_retries(monkeypatch):
    built = []

    def client(service, **kw):
        built.append((service, kw))
        return StubLambda()

    monkeypatch.setattr(boto3, "client", client)
    invoke_crawler()
    service, kw = built[0]
    config = kw["config"]
    assert service == "lambda" and kw["region_name"] == REGION
    assert config.read_timeout > 300
    assert config.retries["total_max_attempts"] == 1
    assert aws.CRAWLER_TIMEOUT_SECONDS == 300


# --- verity crawl -------------------------------------------------------------------------


SUMMARY = {
    "functions": 8,
    "candidates": 1,
    "changes": 0,
    "manifests_invalid": 0,
    "likelihood": {"declared": 3, "none": 4, "probable": 1},
    "written": {"runs": 1},
    "summary": {"largest_evidence_bytes": 812},
}


def test_crawl_without_local_invokes_the_deployed_crawler_and_prints_its_counts(
    monkeypatch, capsys
):
    monkeypatch.setattr(aws, "invoke_crawler", lambda: SUMMARY)
    assert cli.run(["crawl", "--content", str(CONTENT)]) == cli.OK
    out = capsys.readouterr().out
    assert "deployed crawler" in out
    assert "functions: 8" in out and "declared=3" in out
    assert "largest_evidence_bytes=812" in out


def test_a_function_error_is_an_error_exit_that_shows_no_payload(monkeypatch, capsys):
    def fail():
        raise CrawlerFailed("the crawler function returned an error")

    monkeypatch.setattr(aws, "invoke_crawler", fail)
    assert cli.run(["crawl"]) == cli.FAILED
    captured = capsys.readouterr()
    assert "the crawl failed" in captured.err and captured.out.count("\n") == 1


def test_any_other_failure_prints_only_its_type(monkeypatch, capsys):
    def fail():
        raise RuntimeError(f"arn:aws:lambda:{REGION}:{MOTO_ACCOUNT}:function:x {CANARY}")

    monkeypatch.setattr(aws, "invoke_crawler", fail)
    assert cli.run(["crawl"]) == cli.FAILED
    err = capsys.readouterr().err
    assert "RuntimeError" in err and CANARY not in err and MOTO_ACCOUNT not in err


def test_crawl_local_never_invokes_the_crawler(monkeypatch, capsys):
    def boom():
        raise AssertionError("invoked")

    monkeypatch.setattr(aws, "invoke_crawler", boom)
    assert cli.run(["crawl", "--local", "--content", str(CONTENT)]) == cli.OK
    assert "Nothing was read from AWS" in capsys.readouterr().out


def test_load_signals_reads_the_one_file_and_load_content_agrees():
    from verity_core.content.loader import load_content, load_signals

    assert load_signals(CONTENT / SIGNALS) == load_content(CONTENT).signals
