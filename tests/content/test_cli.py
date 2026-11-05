import sys

import pytest
from content_samples import at_scale, broken, good_files, write_tree
from verity_core import cli
from verity_core.graph.memory import InMemoryRepository


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
