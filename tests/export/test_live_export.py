"""The live export path and the decision commit lookup (ADR 0029, decisions 1 and 9; ADR 0030).

The live path is tested against moto and a throwaway git repository. Nothing here reaches AWS:
moto replaces the table, and every person and organisation is invented.
"""

import json
import shutil
import subprocess
from datetime import UTC, datetime
from unittest.mock import patch

import boto3
import pytest
from export_support import CONTENT, FIXTURE, LOADED, NOTHING, ROOT, built_fixture
from moto import mock_aws
from verity_core import cli
from verity_core.assess.apply import apply_assessment
from verity_core.content.seed import seed
from verity_core.discovery.collectors import FixtureCollector
from verity_core.discovery.pipeline import crawl
from verity_core.export import commits, scan
from verity_core.export.build import ScanRejected, build_snapshot, serialise, write_snapshot
from verity_core.export.commits import CommitLookupError
from verity_core.graph.dynamodb.repository import DynamoDBRepository
from verity_core.graph.dynamodb.table import TABLE_NAME, table_definition

DECISIONS = 5


def now() -> datetime:
    return datetime.now(UTC)


def git(repo, *args):
    config = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
    done = subprocess.run(
        ["git", "-C", str(repo), *config, *args], capture_output=True, check=True, text=True
    )
    return done.stdout.strip()


def commit_all(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo_copy(tmp_path):
    """The content and evidence folders in their own git repository, committed once."""
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(CONTENT, root / "content")
    shutil.copytree(ROOT / "evidence", root / "evidence")
    git(root, "init", "-q")
    return root


@pytest.fixture(scope="module")
def table():
    """A moto table holding the seeded, crawled and assessed fixture estate, assessed just now.
    Built once for the module, because filling it takes over a minute. A test that changes it
    must put it back."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        repo = DynamoDBRepository(LOADED.tenant, now, client=client)
        seed(repo, LOADED, now)
        crawl(repo, LOADED, FixtureCollector(FIXTURE), now)
        apply_assessment(repo, LOADED.rules, LOADED.dates, now(), now)
        yield client


def use_table(monkeypatch, client, table_name=TABLE_NAME):
    """`verity export` reads this moto table, not a real client."""
    real = DynamoDBRepository

    def moto_repo(tenant, clock):
        return real(tenant, clock, client=client, table_name=table_name)

    monkeypatch.setattr("verity_core.graph.dynamodb.repository.DynamoDBRepository", moto_repo)


@pytest.fixture
def live(table, monkeypatch):
    use_table(monkeypatch, table)
    return run_export


def run_export(root, *argv):
    return cli.run(["export", "--content", str(root / "content"), *map(str, argv)])


# --- the lookup ---------------------------------------------------------------------------


def test_the_lookup_takes_the_oldest_commit_that_holds_the_recorded_file(tmp_path):
    root = tmp_path
    git(root, "init", "-q")
    path = root / "d.yaml"
    path.write_text("one\n")
    first = commit_all(root, "first")
    (root / "other.txt").write_text("x")
    commit_all(root, "unrelated")
    path.write_text("two\n")
    second = commit_all(root, "edit")
    path.write_text("one\n")  # back to the first content
    third = commit_all(root, "revert")
    import hashlib

    one = hashlib.sha256(b"one\n").hexdigest()
    two = hashlib.sha256(b"two\n").hexdigest()
    assert commits.commit_for(root, "d.yaml", one) == first != third
    assert commits.commit_for(root, "d.yaml", two) == second


def test_the_lookup_finds_nothing_for_an_uncommitted_edit(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "d.yaml").write_text("one\n")
    commit_all(tmp_path, "first")
    (tmp_path / "d.yaml").write_text("edited\n")
    import hashlib

    assert commits.commit_for(tmp_path, "d.yaml", hashlib.sha256(b"edited\n").hexdigest()) is None


def test_the_lookup_reads_only_hashes_not_authors(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "d.yaml").write_text("one\n")
    sha = commit_all(tmp_path, "first")
    import hashlib

    found = commits.commit_for(tmp_path, "d.yaml", hashlib.sha256(b"one\n").hexdigest())
    assert found == sha and len(found) == 40
    rows = commits.without_commits(built_fixture().redacted and _graph())
    assert all(
        set(row) == {"decision_id", "decision_file", "file_sha256", "commit_sha"} for row in rows
    )


def _graph():
    from export_support import fixture_graph

    return fixture_graph()


def test_a_missing_git_is_a_lookup_error(tmp_path):
    with pytest.raises(CommitLookupError):
        commits.commit_for(tmp_path / "nowhere", "d.yaml", "0" * 64)


# --- the fixture source writes null and runs no git ---------------------------------------


def test_a_fixture_export_has_a_null_sha_for_every_decision(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("a fixture export must not run git")

    monkeypatch.setattr(commits.subprocess, "run", forbidden)
    snapshot = built_fixture().snapshot
    assert len(snapshot.decision_commits) == DECISIONS
    assert {row.commit_sha for row in snapshot.decision_commits} == {None}
    assert [row.decision_id for row in snapshot.decision_commits] == sorted(
        row.decision_id for row in snapshot.decision_commits
    )


# --- the scanner's exemption is exact -----------------------------------------------------


SHA = "123456789012" + "a" * 28  # a 12-digit run inside an exact-shape commit SHA


def test_a_commit_sha_under_its_own_key_is_exempt_from_the_digit_rule():
    assert scan.scan({"decision_commits": [{"commit_sha": SHA}]}) == []


@pytest.mark.parametrize(
    "document",
    [
        {"note": SHA},  # right shape, wrong key
        {"commit_sha": SHA + "a"},  # 41 characters
        {"commit_sha": SHA[:-1]},  # 39 characters
        {"commit_sha": SHA[:-1] + "g"},  # not hex
        {"commit_sha": "1234 5678 9012"},  # an account-shaped value under the key
        {"commit_sha": "123456789012"},  # a bare account number under the key
        {"file_sha256": SHA},  # a SHA is not a 64-hex hash
    ],
)
def test_the_exemption_does_not_cover_anything_else(document):
    assert [hit.category for hit in scan.scan(document)] == [scan.ACCOUNT_ID]


# --- the live path ------------------------------------------------------------------------


def test_a_live_export_writes_live_data_with_a_real_sha_per_decision(
    live, repo_copy, tmp_path, capsys
):
    head = commit_all(repo_copy, "content")
    out = tmp_path / "out" / "snapshot.json"
    assert live(repo_copy, "--out", out) == cli.OK
    shown = capsys.readouterr().out
    assert "live graph, read-only" in shown and "scan: clean" in shown
    data = json.loads(out.read_text())
    assert data["header"]["data_source"] == "live"
    assert data["header"]["redaction"]["own_account_replaced"] is True
    rows = data["decision_commits"]
    assert len(rows) == DECISIONS and {row["commit_sha"] for row in rows} == {head}
    assert scan.scan_text(out.read_text()) == []
    assert cli.run(["export", "--check", str(out), "--require-live"]) == cli.OK


def test_a_live_export_is_as_of_now_not_the_start_of_the_day(live, repo_copy, tmp_path):
    commit_all(repo_copy, "content")
    out = tmp_path / "snapshot.json"
    before = now()
    assert live(repo_copy, "--out", out) == cli.OK
    as_of = datetime.fromisoformat(json.loads(out.read_text())["header"]["as_of"])
    assert before <= as_of <= now() and as_of != datetime.combine(
        as_of.date(), as_of.time().min, UTC
    )


def test_a_live_export_refuses_a_decision_with_no_commit(live, repo_copy, tmp_path, capsys):
    # The graph records the file as it was seeded. This edit is committed, so no commit holds
    # the recorded content.
    decision = repo_copy / "content" / "decisions" / "attestation-vc-001-kestrel.yaml"
    decision.write_text(decision.read_text() + "# edited after the graph was seeded\n")
    commit_all(repo_copy, "content")
    out = tmp_path / "snapshot.json"
    assert live(repo_copy, "--out", out) == cli.REFUSED
    err = capsys.readouterr().err
    assert "attestation-vc-001-kestrel" in err and "1 decision(s)" in err and not out.exists()


def test_a_live_export_outside_a_git_checkout_is_refused(live, repo_copy, tmp_path, capsys):
    out = tmp_path / "snapshot.json"  # the copy was never `git init`-committed
    assert live(repo_copy, "--out", out) == cli.REFUSED
    assert "refused:" in capsys.readouterr().err and not out.exists()


def test_a_live_export_of_an_unassessed_table_is_refused(table, live, repo_copy, tmp_path, capsys):
    commit_all(repo_copy, "content")
    # An assessment now would write one that is missing: delete a stored one, then restore it.
    key = {"PK": {"S": f"T#{LOADED.tenant}#N#{_an_assessment_id()}"}, "SK": {"S": "META"}}
    item = table.get_item(TableName=TABLE_NAME, Key=key)["Item"]
    table.delete_item(TableName=TABLE_NAME, Key=key)
    try:
        out = tmp_path / "snapshot.json"
        assert live(repo_copy, "--out", out) == cli.REFUSED
        assert "run verity assess first" in capsys.readouterr().err and not out.exists()
    finally:
        table.put_item(TableName=TABLE_NAME, Item=item)


def _an_assessment_id():
    from verity_core.model.nodes import ControlAssessment

    graph = _graph()
    return next(n for n in sorted(graph) if isinstance(graph.nodes[n]["record"], ControlAssessment))


def test_a_live_export_of_an_empty_table_is_refused(
    table, monkeypatch, repo_copy, tmp_path, capsys
):
    table.create_table(**table_definition("verity-empty"))
    use_table(monkeypatch, table, "verity-empty")
    assert run_export(repo_copy, "--out", tmp_path / "s.json") == cli.REFUSED
    assert "table is empty" in capsys.readouterr().err


@pytest.mark.parametrize("flag", [["--as-of", "2026-11-06"], ["--fixture", str(FIXTURE)]])
def test_a_live_export_takes_no_as_of_or_fixture(flag, tmp_path, capsys):
    out = tmp_path / "snapshot.json"
    assert cli.run(["export", "--content", str(CONTENT), "--out", str(out), *flag]) == cli.REFUSED
    assert "only go with --local" in capsys.readouterr().err and not out.exists()


def test_a_live_export_must_show_the_owners_account():
    graph = _graph().copy()
    graph.remove_nodes_from([n for n in list(graph) if n.startswith("ev:")])
    # Patching the estimate skips the stale check, which the removal would otherwise trip first.
    with (
        patch("verity_core.export.build.estimate_apply", return_value=NOTHING),
        pytest.raises(ValueError, match="owner's account"),
    ):
        build_snapshot(graph, content=LOADED, as_of=now(), data_source="live")


def test_the_scan_still_runs_on_a_live_export(live, repo_copy, tmp_path, monkeypatch):
    commit_all(repo_copy, "content")
    monkeypatch.setattr(
        "verity_core.export.build.scan_text",
        lambda text, **kw: [scan.Hit(scan.ACCOUNT_ID, "$.x")],
    )
    out = tmp_path / "snapshot.json"
    assert live(repo_copy, "--out", out) == cli.FAILED and not out.exists()


def test_serialise_and_write_still_agree_for_the_new_rows(tmp_path):
    built = built_fixture()
    out = tmp_path / "s.json"
    write_snapshot(out, built)
    assert out.read_text(encoding="utf-8") == serialise(built.snapshot)
    assert ScanRejected  # imported for the type of failure the live path shares


# --- AWS errors on the live path show their type only ----------------------------------------

LEAK = "111122223333"  # invented; stands for an account ID that an AWS message could quote


def _client_error():
    from botocore.exceptions import ClientError

    message = f"User: arn:aws:iam::{LEAK}:user/someone is not authorized"
    return ClientError({"Error": {"Code": "AccessDeniedException", "Message": message}}, "Scan")


def _connection_error():
    from botocore.exceptions import EndpointConnectionError

    return EndpointConnectionError(endpoint_url=f"https://dynamodb.eu-north-1.{LEAK}.example/")


def _no_credentials():
    from botocore.exceptions import NoCredentialsError

    return NoCredentialsError()


@pytest.mark.parametrize(
    ("make", "name"),
    [
        (_client_error, "ClientError"),
        (_connection_error, "EndpointConnectionError"),
        (_no_credentials, "NoCredentialsError"),
    ],
)
@pytest.mark.parametrize("where", ["load_graph", "construct"])
def test_an_aws_error_on_the_live_path_prints_only_its_type(
    make, name, where, monkeypatch, repo_copy, tmp_path, capsys
):
    class Broken:
        def __init__(self, tenant, clock):
            if where == "construct":
                raise make()

        def load_graph(self):
            raise make()

    monkeypatch.setattr("verity_core.graph.dynamodb.repository.DynamoDBRepository", Broken)
    out = tmp_path / "snapshot.json"
    assert run_export(repo_copy, "--out", out) == cli.UNREADABLE
    captured = capsys.readouterr()
    assert captured.err.strip() == f"cannot build the snapshot: {name}"
    assert LEAK not in captured.out + captured.err and "arn:" not in captured.out + captured.err
    assert not out.exists()


def test_a_local_export_still_needs_no_aws_error_types(monkeypatch, tmp_path):
    """The botocore import sits on the live branch only, so --local imports no AWS library."""
    import sys

    for name in [n for n in sys.modules if n == "botocore" or n.startswith("botocore.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(sys, "meta_path", [_Block(), *sys.meta_path])
    out = tmp_path / "snapshot.json"
    assert cli.run(["export", "--content", str(CONTENT), "--local", "--out", str(out)]) == cli.OK


class _Block:
    """Refuses `import botocore`, so the test fails if the local path imports it."""

    def find_spec(self, name, path=None, target=None):
        if name == "botocore" or name.startswith("botocore."):
            raise ImportError("botocore must not be imported by a local export")
        return None
