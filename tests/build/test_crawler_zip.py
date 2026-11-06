"""The crawler's and the probe's handlers, run from their built zips (ADR 0025).

Each zip is extracted and its handler runs in a subprocess, with moto started in the child. The
environment is built from nothing, the credentials are fake and no endpoint is set, so moto
answers every call and nothing can reach AWS. The child refuses to continue if it finds a
credential that is not the fake one.

The zip's arm64 Linux `.so` files cannot load on this machine, so they are deleted from the
extraction (as `test_zip_handlers.py` does for pydantic) and the host's compiled packages answer.
What must still come from the extraction is every `verity_core`, `networkx` and `yaml` module,
and the pure-Python part of pydantic: a file missing from the zip would otherwise be found in the
repository's own environment and pass unseen.
"""

import json
import shutil
import subprocess
import sys
import zipfile

import pytest

CHILD = r"""
import json, os, sys

work = sys.argv[1]
mode = sys.argv[2]
assert os.environ["AWS_ACCESS_KEY_ID"] == "testing", "refusing to run with a real credential"
sys.path.insert(0, work)

import boto3
from moto import mock_aws

CANARY = "VERITY-CANARY-7f3a"
TRUST = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
         "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}


class Trail:
    def get_paginator(self, operation):
        return self

    def paginate(self, **arguments):
        yield {"Events": []}


import app

out = {}
with mock_aws():
    dynamodb = boto3.client("dynamodb", region_name="eu-north-1")
    if mode == "crawler":
        from verity_core.graph.dynamodb.table import table_definition

        dynamodb.create_table(**table_definition())
        import io, zipfile
        iam = boto3.client("iam", region_name="eu-north-1")
        iam.create_role(RoleName="shadow-role", AssumeRolePolicyDocument=json.dumps(TRUST))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("app.py", "def handler(event, context):\n    return {}\n")
        boto3.client("lambda", region_name="eu-north-1").create_function(
            FunctionName="shadow-summariser", Runtime="python3.12",
            Role="arn:aws:iam::123456789012:role/shadow-role", Handler="app.handler",
            Code={"ZipFile": buffer.getvalue()}, Architectures=["arm64"],
            Environment={"Variables": {"OPENAI_BASE_URL": CANARY}},
        )
        original = app.AwsClients.create
        app.AwsClients.create = staticmethod(
            lambda region="eu-north-1": __import__("dataclasses").replace(
                original(region), cloudtrail=Trail()
            )
        )
        out["first"] = app.handler({}, None)
        out["second"] = app.handler({}, None)
    else:  # the probe zip has no `table` module: a plain table is enough
        dynamodb.create_table(
            TableName="verity-graph",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                       {"AttributeName": "SK", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"},
                                  {"AttributeName": "SK", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        for pk, sk in (("T#kestrel#N#sys:support-assistant", "META"),
                       ("T#kestrel#U#sys:contract-insights", "U#probe")):
            dynamodb.put_item(TableName="verity-graph", Item={
                "PK": {"S": pk}, "SK": {"S": sk}, "doc": {"S": "original"}})
        before = dynamodb.scan(TableName="verity-graph")["Items"]
        out["result"] = app.handler({}, None)
        out["unchanged"] = dynamodb.scan(TableName="verity-graph")["Items"] == before

ours = {"verity_core", "pydantic", "typing_extensions", "annotated_types"}
if mode == "crawler":  # moto itself imports yaml, so only the crawler's own use is checked
    ours |= {"networkx", "yaml"}
out["foreign"] = sorted(
    name for name, module in sys.modules.items()
    if name.split(".")[0] in ours and getattr(module, "__file__", None)
    and not module.__file__.startswith(work)
)
out["loaded"] = sorted({name.split(".")[0] for name in sys.modules} & ours)
print(json.dumps(out))
"""

FAKE_ENV = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_REGION": "eu-north-1",
    "AWS_DEFAULT_REGION": "eu-north-1",
    "AWS_EC2_METADATA_DISABLED": "true",
    "AWS_CONFIG_FILE": "/nonexistent/config",
    "AWS_SHARED_CREDENTIALS_FILE": "/nonexistent/credentials",
}


def extract(zips, function, tmp_path_factory):
    target = tmp_path_factory.mktemp(f"run-{function}")
    with zipfile.ZipFile(zips[function]) as archive:
        archive.extractall(target)
    for path in target.rglob("*.so"):  # arm64 Linux: cannot load here
        path.unlink()
    shutil.rmtree(target / "pydantic_core", ignore_errors=True)
    return target


def run(work, mode, env_extra):
    done = subprocess.run(
        [sys.executable, "-I", "-c", CHILD, str(work), mode],
        env={**FAKE_ENV, **env_extra},
        capture_output=True,
        text=True,
        timeout=120,
        cwd=work,
    )
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1]), done


@pytest.fixture(scope="module")
def crawler_run(builds, tmp_path_factory):
    _, zips, _ = builds
    work = extract(zips, "verity-crawler", tmp_path_factory)
    env = {
        "GRAPH_TABLE": "verity-graph",
        "TENANT": "kestrel",
        "SIGNALS_FILE": "rules/ai_signals.yaml",
    }
    return run(work, "crawler", env)


def test_the_crawler_zip_crawls_a_moto_account_from_the_extraction(crawler_run):
    out, _ = crawler_run
    assert out["first"]["functions"] == 1
    assert sum(out["first"]["written"].values()) > 1
    assert out["second"]["written"] == {"runs": 1}


def test_every_verity_core_networkx_and_yaml_module_loads_from_the_extraction(crawler_run):
    out, _ = crawler_run
    assert out["foreign"] == []
    assert {"verity_core", "networkx", "yaml", "pydantic"} <= set(out["loaded"])


def test_the_crawler_result_and_output_hold_no_name_arn_account_or_canary(crawler_run):
    out, done = crawler_run
    text = json.dumps([out["first"], out["second"]]) + done.stdout + done.stderr
    for forbidden in ("shadow-summariser", "shadow-role", "arn:", "123456789012", "VERITY-CANARY"):
        assert forbidden not in text


def test_the_probe_zip_leaves_the_table_unchanged_from_the_extraction(builds, tmp_path_factory):
    _, zips, _ = builds
    work = extract(zips, "verity-probe", tmp_path_factory)
    out, _ = run(work, "probe", {"GRAPH_TABLE": "verity-graph"})
    assert out["result"] == {
        "own_meta": "ConditionalCheckFailedException",
        "other_usage": "ConditionalCheckFailedException",
    }
    assert out["unchanged"] is True
    assert out["foreign"] == []
    assert "networkx" not in out["loaded"]
