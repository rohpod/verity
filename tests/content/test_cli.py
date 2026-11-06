import shutil
import sys
from pathlib import Path

import pytest
from content_samples import at_scale, broken, good_files, write_tree
from verity_core import cli
from verity_core.graph.memory import InMemoryRepository
from verity_core.model.enums import NodeType


def tree(tmp_path, files=None):
    files = files if files is not None else broken(at_scale)
    return str(write_tree(tmp_path, files))


@pytest.fixture
def fake_table(monkeypatch):
    """Stands in for the real repository, and records whether the CLI built one."""
    built = []

    def factory(tenant, clock):
        built.append(tenant)
        return InMemoryRepository(tenant, clock)

    monkeypatch.setattr("verity_core.graph.dynamodb.repository.DynamoDBRepository", factory)
    return built


def test_lint_passes_good_content(tmp_path, capsys):
    assert cli.run(["lint", "--content", tree(tmp_path)]) == cli.OK
    assert "content passes lint" in capsys.readouterr().out


def test_lint_lists_every_issue_and_fails(tmp_path, capsys):
    assert cli.run(["lint", "--content", tree(tmp_path, good_files())]) == cli.LINT_FAILED
    err = capsys.readouterr().err
    assert "control_count" in err
    assert "1 lint issue(s)" in err


def test_unreadable_content_exits_with_its_own_code(tmp_path, capsys):
    root = tree(tmp_path)
    (tmp_path / "controls.yaml").write_text("controls: [unclosed")
    assert cli.run(["lint", "--content", root]) == cli.UNREADABLE
    assert "cannot read content" in capsys.readouterr().err


def test_seed_defaults_to_a_dry_run_that_never_builds_the_real_repository(
    tmp_path, capsys, fake_table
):
    assert cli.run(["seed", "--content", tree(tmp_path)]) == cli.OK
    out = capsys.readouterr().out
    assert "dry run only" in out
    assert "write units" in out
    assert fake_table == []


def test_the_real_target_is_refused_without_confirmation(tmp_path, capsys, fake_table):
    assert cli.run(["seed", "--content", tree(tmp_path), "--target", "dynamodb"]) == cli.REFUSED
    assert "not confirmed" in capsys.readouterr().err
    assert fake_table == []


def test_the_prompt_must_be_answered_exactly(tmp_path, monkeypatch, fake_table):
    root = tree(tmp_path)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    assert cli.run(["seed", "--content", root, "--target", "dynamodb"]) == cli.REFUSED
    monkeypatch.setattr("builtins.input", lambda prompt: "seed")
    assert cli.run(["seed", "--content", root, "--target", "dynamodb"]) == cli.OK
    assert fake_table == ["kestrel"]


def test_the_real_target_seeds_with_yes_and_reports_progress(tmp_path, capsys, fake_table):
    args = ["seed", "--content", tree(tmp_path), "--target", "dynamodb", "--yes"]
    assert cli.run(args) == cli.OK
    captured = capsys.readouterr()
    assert "nodes: 35 written, 0 unchanged; edges: 35 written, 0 unchanged" in captured.out
    assert "  nodes: 35/35" in captured.err
    assert "  edges: 35/35" in captured.err
    assert fake_table == ["kestrel"]


def test_a_lint_failure_stops_the_seed_before_the_table_is_touched(tmp_path, capsys, fake_table):
    args = ["seed", "--content", tree(tmp_path, good_files()), "--target", "dynamodb", "--yes"]
    assert cli.run(args) == cli.LINT_FAILED
    assert fake_table == []


def test_the_tenant_is_passed_through(tmp_path, fake_table):
    args = ["seed", "--content", tree(tmp_path), "--target", "dynamodb", "--yes"]
    assert cli.run([*args, "--tenant", "acme"]) == cli.OK
    assert fake_table == ["acme"]


def test_main_exits_with_the_status(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["verity", "lint", "--content", str(tmp_path)])
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == cli.LINT_FAILED


def test_a_command_is_required():
    with pytest.raises(SystemExit):
        cli.run([])


# --- assess and attest (M5) ---------------------------------------------------------------

REAL_CONTENT = str(Path(__file__).parents[2] / "content")


def test_assess_defaults_to_a_dry_run_that_never_builds_the_real_repository(capsys, fake_table):
    assert cli.run(["assess", "--content", REAL_CONTENT, "--as-of", "2026-11-05"]) == cli.OK
    out = capsys.readouterr().out
    assert "dry run only" in out
    assert "high   no_evidence" in out
    assert "1 satisfied (1 on simulated sign-offs)" in out
    assert "applicability: " in out
    assert fake_table == []


def test_assess_lists_every_finding_with_verbose(capsys):
    args = ["assess", "--content", REAL_CONTENT, "--as-of", "2026-11-05", "--verbose"]
    assert cli.run(args) == cli.OK
    assert "no_owner  sys:legacy-faq-bot" in capsys.readouterr().out


def test_assess_can_be_limited_to_one_system(capsys):
    args = ["assess", "--content", REAL_CONTENT, "--as-of", "2026-11-05", "--system"]
    assert cli.run([*args, "sys:talent-screening"]) == cli.OK
    assert "no_owner" not in capsys.readouterr().out


def test_assess_refuses_an_unknown_system_without_a_traceback(capsys):
    args = ["assess", "--content", REAL_CONTENT, "--as-of", "2026-11-05", "--system", "sys:nope"]
    assert cli.run(args) == cli.REFUSED
    assert "'sys:nope' is not a system" in capsys.readouterr().err


def test_assess_without_rules_cannot_run(tmp_path, capsys):
    assert cli.run(["assess", "--content", tree(tmp_path)]) == cli.UNREADABLE
    assert "applicability.yaml is missing" in capsys.readouterr().err


def test_the_real_table_is_assessed_only_as_of_today(capsys, fake_table):
    args = ["assess", "--content", REAL_CONTENT, "--as-of", "2020-01-01", "--target", "dynamodb"]
    assert cli.run(args) == cli.REFUSED
    assert "only assessed as of today" in capsys.readouterr().err
    assert fake_table == []


def test_the_real_table_must_be_seeded_first(capsys, fake_table):
    assert cli.run(["assess", "--content", REAL_CONTENT, "--target", "dynamodb"]) == cli.REFUSED
    assert "run `verity seed" in capsys.readouterr().err


def test_the_real_target_is_refused_without_confirmation_and_prints_the_estimate(
    capsys, fake_table, monkeypatch
):
    from verity_core.content.loader import load_content
    from verity_core.content.seed import seed

    content = load_content(REAL_CONTENT)
    stored = {}

    def factory(tenant, clock):
        stored.setdefault("repo", InMemoryRepository(tenant, clock))
        return stored["repo"]

    monkeypatch.setattr("verity_core.graph.dynamodb.repository.DynamoDBRepository", factory)
    seed(factory("kestrel", cli._utc_now), content, cli._utc_now)
    assert cli.run(["assess", "--content", REAL_CONTENT, "--target", "dynamodb"]) == cli.REFUSED
    captured = capsys.readouterr()
    assert "estimated writes" in captured.out
    assert "not confirmed" in captured.err
    assert not stored["repo"].nodes_by_type(NodeType.CONTROL_ASSESSMENT)


def test_attest_scaffolds_a_decision_file_and_refuses_to_overwrite(tmp_path, capsys):
    args = ["attest", "VC-001", "org:kestrel", "--by", "person:l-ivanova"]
    args += ["--content", str(tmp_path)]
    assert cli.run(args) == cli.OK
    (path,) = (tmp_path / "decisions").glob("*.yaml")
    text = path.read_text()
    assert "kind: attestation" in text and "status: partially_implemented" in text
    assert "simulated: true" in text
    assert "Simulated sign-off by a fictional person." in text
    assert cli.run(args) == cli.REFUSED
    assert "already exists" in capsys.readouterr().err


def test_an_unedited_attest_scaffold_fails_lint(tmp_path, capsys):
    shutil.copytree(REAL_CONTENT, tmp_path / "content")
    shutil.copytree(Path(REAL_CONTENT).parent / "evidence", tmp_path / "evidence")
    content = str(tmp_path / "content")
    args = ["attest", "VC-002", "org:kestrel", "--by", "person:l-ivanova", "--content", content]
    assert cli.run(args) == cli.OK
    assert cli.run(["lint", "--content", content]) == cli.LINT_FAILED
    assert "decision_todo" in capsys.readouterr().err


def test_attest_refuses_an_invalid_control(tmp_path, capsys):
    args = ["attest", "NOPE", "org:kestrel", "--by", "person:l-ivanova", "--content", str(tmp_path)]
    assert cli.run(args) == cli.UNREADABLE
    assert not (tmp_path / "decisions").exists()


def test_attest_never_touches_the_graph(tmp_path, fake_table):
    args = ["attest", "VC-001", "org:kestrel", "--by", "person:l-ivanova"]
    cli.run([*args, "--content", str(tmp_path)])
    assert fake_table == []


def test_the_module_runs_as_a_script():
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "verity_core.cli", "lint", "--content", REAL_CONTENT],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "content passes lint" in out


# --- verity crawl (M6) ---------------------------------------------------------------------

REAL = Path(__file__).parents[2] / "content"


def test_crawl_without_local_is_refused_and_names_m8(capsys):
    assert cli.run(["crawl", "--content", str(REAL)]) == cli.REFUSED
    err = capsys.readouterr().err
    assert err.startswith("refused:") and "M8" in err


def test_crawl_local_scores_the_fixture_and_assesses_it(capsys):
    assert cli.run(["crawl", "--local", "--content", str(REAL)]) == cli.OK
    out = capsys.readouterr().out
    assert "recorded fixture" in out and "Nothing was read from AWS" in out
    assert "shadow-summariser    probable" in out
    assert "invoice-renderer     none" in out
    assert "high   shadow_ai_candidate  cand:shadow-summariser" in out
    assert "high   control_not_met  sys:support-assistant" in out
    assert "dry run only" in out


def test_crawl_local_never_prints_an_env_value_or_an_account_id(capsys):
    assert cli.run(["crawl", "--local", "--verbose", "--content", str(REAL)]) == cli.OK
    out = capsys.readouterr()
    assert "VERITY-CANARY-7f3a" not in out.out + out.err
    assert "000000000000" not in out.out + out.err
    assert "run summary:" in out.out


def test_crawl_local_reads_another_fixture(tmp_path, capsys):
    import json

    raw = json.loads((REAL / "fixtures" / "crawl" / "estate.json").read_text())
    raw["functions"] = [f for f in raw["functions"] if f["FunctionName"] != "shadow-summariser"]
    path = tmp_path / "estate.json"
    path.write_text(json.dumps(raw))
    assert cli.run(["crawl", "--local", "--fixture", str(path), "--content", str(REAL)]) == cli.OK
    assert "shadow-summariser" not in capsys.readouterr().out


def test_crawl_local_with_a_missing_or_broken_fixture_is_unreadable(tmp_path, capsys):
    missing = tmp_path / "nope.json"
    assert cli.run(["crawl", "--local", "--fixture", str(missing), "--content", str(REAL)]) == (
        cli.UNREADABLE
    )
    broken = tmp_path / "broken.json"
    broken.write_text('{"functions": [{"FunctionName": "f"}]}')
    assert cli.run(["crawl", "--local", "--fixture", str(broken), "--content", str(REAL)]) == (
        cli.UNREADABLE
    )
    assert "cannot read the fixture" in capsys.readouterr().err


def test_crawl_local_needs_the_signals_file(tmp_path, capsys):
    assert cli.run(["crawl", "--local", "--content", tree(tmp_path)]) == cli.UNREADABLE
    assert "ai_signals.yaml" in capsys.readouterr().err


def test_crawl_local_does_not_import_the_aws_collector():
    import subprocess

    code = (
        "import sys; from verity_core import cli; "
        f"assert cli.run(['crawl', '--local', '--content', {str(REAL)!r}]) == 0; "
        "assert 'verity_core.discovery.aws' not in sys.modules; "
        "assert 'boto3' not in sys.modules"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
