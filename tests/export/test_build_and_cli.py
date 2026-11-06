"""Writing the snapshot, the `verity export` command and its guarantees (ADR 0029)."""

import json

import pytest
from export_support import (
    CONTENT,
    FIXTURE,
    built_fixture,
    built_from,
    function_config,
    small_graph,
)
from verity_core import cli
from verity_core.export import scan
from verity_core.export.build import ScanRejected, serialise, write_snapshot

EMAIL = "someone" + "@" + "example." + "com"


def run(*argv):
    return cli.run(["export", "--content", str(CONTENT), *map(str, argv)])


# --- identical inputs, identical bytes ---------------------------------------------------


def test_identical_inputs_and_as_of_give_identical_bytes():
    first = serialise(built_fixture().snapshot)
    second = serialise(built_fixture().snapshot)
    assert first == second and first.endswith("\n")


def test_the_command_gives_identical_files_for_the_same_as_of(tmp_path):
    for name in ("a", "b"):
        assert run("--local", "--as-of", "2026-11-06", "--out", tmp_path / f"{name}.json") == cli.OK
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


def test_a_different_as_of_gives_a_different_file(tmp_path):
    run("--local", "--as-of", "2026-11-06", "--out", tmp_path / "a.json")
    run("--local", "--as-of", "2026-11-07", "--out", tmp_path / "b.json")
    assert (tmp_path / "a.json").read_bytes() != (tmp_path / "b.json").read_bytes()


# --- the fail-closed write ---------------------------------------------------------------


def test_a_scan_hit_leaves_no_file_behind(tmp_path):
    graph, _ = small_graph({"ai_actions": [EMAIL]})
    target = tmp_path / "out" / "snapshot.json"
    with pytest.raises(ScanRejected) as rejected:
        write_snapshot(target, built_from(graph))
    assert [h.category for h in rejected.value.hits] == [scan.EMAIL]
    assert not target.exists()
    assert list(tmp_path.rglob("*")) == []  # not a temporary file, not even the folder


def test_a_scan_hit_does_not_replace_an_existing_file(tmp_path):
    target = tmp_path / "snapshot.json"
    target.write_text("previous")
    graph, _ = small_graph({"ai_actions": [EMAIL]})
    with pytest.raises(ScanRejected):
        write_snapshot(target, built_from(graph))
    assert target.read_text() == "previous"
    assert [p.name for p in tmp_path.iterdir()] == ["snapshot.json"]


def test_a_clean_graph_is_written_and_nothing_else_is_left(tmp_path):
    target = tmp_path / "snapshot.json"
    size = write_snapshot(target, built_from(small_graph(function_config("acct_0a1b2c3d"))[0]))
    assert size == target.stat().st_size
    assert [p.name for p in tmp_path.iterdir()] == ["snapshot.json"]


def test_the_file_the_scan_read_is_the_file_that_was_renamed(tmp_path):
    target = tmp_path / "snapshot.json"
    built = built_fixture()
    write_snapshot(target, built)
    assert target.read_text() == serialise(built.snapshot)
    assert scan.scan_text(target.read_text(), old_hashes=built.redacted.replaced_hashes) == []


def test_the_command_writes_nothing_when_the_scan_finds_something(tmp_path, capsys):
    fixture = json.loads(FIXTURE.read_text())
    fixture["tag_mappings"][0]["Tags"].append({"Key": "project", "Value": EMAIL})
    path = tmp_path / "estate.json"
    path.write_text(json.dumps(fixture))
    out = tmp_path / "snapshot.json"
    assert run("--local", "--as-of", "2026-11-06", "--fixture", path, "--out", out) == cli.FAILED
    captured = capsys.readouterr()
    assert not out.exists() and list(tmp_path.glob(".snapshot-*")) == []
    assert "scan hit: email at $.nodes[" in captured.err and "tags.project" in captured.err
    assert EMAIL not in captured.err + captured.out
    assert "nothing was written" in captured.err


# --- the command -------------------------------------------------------------------------


def test_export_local_reports_what_it_did_and_stays_small(tmp_path, capsys):
    out = tmp_path / "snapshot.json"
    assert run("--local", "--as-of", "2026-11-06", "--out", out) == cli.OK
    text = capsys.readouterr().out
    assert "Nothing was read from AWS" in text and "scan: clean" in text
    assert "own account replaced" in text and "Evidence rebuilt" in text
    assert out.stat().st_size < 2 * 1024 * 1024
    data = json.loads(out.read_text())
    assert data["header"]["data_source"] == "fixture" and data["header"]["schema_version"] == 1
    assert data["header"]["as_of"] == "2026-11-06T00:00:00Z"


def test_export_check_passes_a_clean_file_and_fails_a_planted_one(tmp_path, capsys):
    clean = tmp_path / "clean.json"
    run("--local", "--as-of", "2026-11-06", "--out", clean)
    capsys.readouterr()
    assert run("--check", clean) == cli.OK
    assert "0 scan hit(s)" in capsys.readouterr().out
    dirty = tmp_path / "dirty.json"
    data = json.loads(clean.read_text())
    data["nodes"][0]["name"] = "owner " + EMAIL
    dirty.write_text(json.dumps(data))
    assert run("--check", dirty) == cli.FAILED
    err = capsys.readouterr().err
    assert "email at $.nodes[0].name" in err and EMAIL not in err


def test_export_check_on_a_missing_file_is_an_error(tmp_path, capsys):
    assert run("--check", tmp_path / "missing.json") == cli.UNREADABLE


def test_a_local_export_does_not_import_the_aws_collector():
    import subprocess
    import sys

    code = (
        "import sys, tempfile, pathlib; from verity_core import cli; "
        f"out = pathlib.Path(tempfile.mkdtemp()) / 's.json'; "
        f"assert cli.run(['export', '--local', '--content', {str(CONTENT)!r}, '--as-of', "
        "'2026-11-06', '--out', str(out)]) == 0; "
        "assert 'boto3' not in sys.modules, 'boto3 was imported'"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-800:]


def test_the_default_output_is_a_folder_git_ignores():
    parser = cli.build_parser()
    assert str(parser.parse_args(["export", "--local"]).out) == ".build/snapshot.json"
    assert ".build/" in (CONTENT.parent / ".gitignore").read_text()
