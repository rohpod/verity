"""The dashboard's test data cannot drift from the export (ADR 0031, decisions 4 and 12).

`web/src/test/mini-snapshot.json` is invented data written through the export code, and
`mini-expected.json` is Python's `stale_by_change` answer for it. The dashboard's tests read both.
"""

import json
import sys

from export_support import ROOT
from verity_core.export import scan
from verity_core.export.snapshot import Snapshot

MINI = ROOT / "web" / "src" / "test" / "mini-snapshot.json"
EXPECTED = ROOT / "web" / "src" / "test" / "mini-expected.json"
AUDIT = ROOT / "web" / "src" / "test" / "mini-audit.json"


def script():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import write_ui_fixtures as module
    finally:
        sys.path.pop(0)
    return module


def test_the_committed_mini_files_are_the_ones_the_export_gives():
    snapshot, expected, audit = script().mini_outputs()
    assert MINI.read_text(encoding="utf-8") == snapshot
    assert EXPECTED.read_text(encoding="utf-8") == expected
    assert AUDIT.read_text(encoding="utf-8") == audit


def test_the_mini_audit_path_crosses_the_redaction_id_map():
    """The recorded fixture's audit paths hold no redacted Evidence, so this is the case that
    proves the map: the config Evidence that supports the assessment has a new ID and hash."""
    data = json.loads(MINI.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    published = {n["id"]: n for n in data["nodes"] if n["type"] == "Evidence"}
    ids = [e["evidenceId"] for row in audit for link in row["links"] for e in link["evidence"]]
    redacted = [i for i in ids if published[i]["redacted"]]
    assert redacted, "no redacted Evidence on an audit path"
    for row in audit:
        for link in row["links"]:
            for e in link["evidence"]:
                assert e["sha256"] == published[e["evidenceId"]]["sha256"]


def test_the_mini_snapshot_validates_against_the_snapshot_model_and_scans_clean():
    text = MINI.read_text(encoding="utf-8")
    Snapshot.model_validate_json(text)
    assert scan.scan_text(text) == []


def test_the_mini_snapshot_fills_the_fixtures_gaps():
    data = json.loads(MINI.read_text(encoding="utf-8"))
    types = {n["type"] for n in data["nodes"]}
    assert "ChangeEvent" in types
    assert any(n["source"] == "discovered" for n in data["nodes"])
    assert data["header"]["data_source"] == "fixture"


def test_only_evidence_collected_before_the_change_is_stale_in_pythons_answer():
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    data = json.loads(MINI.read_text(encoding="utf-8"))
    change = next(n for n in data["nodes"] if n["type"] == "ChangeEvent")
    by_id = {n["id"]: n for n in data["nodes"]}
    stale = [by_id[e["evidenceId"]] for e in expected["evidence"]]
    assert stale and all(e["collected_at"] < change["detected_at"] for e in stale)
    collected_after = [
        n
        for n in data["nodes"]
        if n["type"] == "Evidence" and n["collected_at"] > change["detected_at"]
    ]
    assert collected_after and not {n["id"] for n in collected_after} & {
        e["evidenceId"] for e in expected["evidence"]
    }
