"""What the M9 redaction review found (ADR 0030). Each test failed, or would not have noticed the
fault, before the fix. Everything here is invented."""

import json
import stat
from datetime import timedelta

import pytest
from export_support import (
    AS_OF,
    COMMON,
    LOADED,
    OTHER,
    OWN,
    ROOT,
    built_fixture,
    built_from,
    evidence,
    fixture_graph,
    function_config,
    small_graph,
)
from verity_core import cli
from verity_core.export import scan
from verity_core.export.build import (
    MAX_SNAPSHOT_BYTES,
    ScanRejected,
    SnapshotTooLarge,
    build_snapshot,
    serialise,
    write_snapshot,
)
from verity_core.export.fields import (
    PUBLIC_CONTENT_KEYS,
    WITHHELD_CONTENT_KEYS,
)
from verity_core.export.redact import OWN_ACCOUNT, RedactionError
from verity_core.export.snapshot import Snapshot
from verity_core.model.edges import PlainEdge
from verity_core.model.enums import EdgeType, EvidenceKind, Source
from verity_core.model.evidence import content_sha256
from verity_core.model.nodes import AWSResource, ChangeEvent, DiscoveryRun, Evidence, Risk

ACCOUNT = "123456789012"
PERSON = "Jane Invented"


def document(built):
    return json.loads(serialise(built.snapshot))


def resource(**fields):
    return AWSResource(
        id=fields.pop("id", "res:lambda:planted"),
        resource_type="lambda",
        region="eu-north-1",
        name="planted",
        **COMMON,
        **fields,
    )


def add(graph, *records):
    for record in records:
        graph.add_node(record.id, record=record)
    return graph


# --- finding 1: nothing unscanned touches the disk ---------------------------------------


def test_the_scan_runs_before_anything_is_written(tmp_path, monkeypatch):
    graph, _ = small_graph(function_config(OWN))
    built = built_from(graph)
    order = []
    real_scan, real_mkstemp = scan.scan_text, __import__("tempfile").mkstemp
    monkeypatch.setattr(
        "verity_core.export.build.scan_text",
        lambda *a, **k: order.append("scan") or real_scan(*a, **k),
    )
    monkeypatch.setattr(
        "verity_core.export.build.tempfile.mkstemp",
        lambda *a, **k: order.append("write") or real_mkstemp(*a, **k),
    )
    write_snapshot(tmp_path / "snapshot.json", built)
    assert order == ["scan", "write"]


def test_a_failure_before_the_rename_leaves_nothing_behind(tmp_path, monkeypatch):
    graph, _ = small_graph(function_config(OWN))
    built = built_from(graph)

    def crash(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr("verity_core.export.build.os.replace", crash)
    with pytest.raises(KeyboardInterrupt):
        write_snapshot(tmp_path / "snapshot.json", built)
    assert list(tmp_path.iterdir()) == []


def test_a_written_snapshot_can_be_read_by_anyone(tmp_path):
    graph, _ = small_graph(function_config(OWN))
    path = tmp_path / "snapshot.json"
    write_snapshot(path, built_from(graph))
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_a_temporary_snapshot_is_ignored_by_git():
    assert ".snapshot-*.tmp" in (ROOT / ".gitignore").read_text()


def test_a_snapshot_over_the_limit_is_refused(tmp_path, monkeypatch):
    graph, _ = small_graph(function_config(OWN))
    built = built_from(graph)
    monkeypatch.setattr("verity_core.export.build.MAX_SNAPSHOT_BYTES", 10)
    target = tmp_path / "snapshot.json"
    with pytest.raises(SnapshotTooLarge):
        write_snapshot(target, built)
    assert not target.exists()


def test_the_fixture_is_well_under_the_limit():
    assert len(serialise(built_fixture().snapshot).encode()) < MAX_SNAPSHOT_BYTES * 0.7


# --- finding 2: the scanner cannot be passed by spelling ---------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "1" + ACCOUNT,
        ACCOUNT + ACCOUNT,
        "1234-5678-9012",
        "1234 5678 9012",
        int("1" + ACCOUNT),
        float(ACCOUNT),
        1.23456789012e11,
    ],
)
def test_digits_hidden_in_a_longer_run_or_groups_are_an_account(value):
    assert scan.ACCOUNT_ID in {h.category for h in scan.scan({"k": value})}


def test_the_digits_of_a_fraction_are_not_an_account():
    assert scan.scan({"k": 0.203377625696288}) == []


@pytest.mark.parametrize(
    "value", ["ev:" + ACCOUNT, "ev:" + ACCOUNT + "ab", ACCOUNT + "a" * 52, ACCOUNT + "0" * 52]
)
def test_a_value_shaped_like_a_hash_is_exempt_only_where_a_hash_belongs(value):
    assert scan.ACCOUNT_ID in {h.category for h in scan.scan({"description": value})}


def test_a_real_hash_and_evidence_id_are_exempt_where_they_belong():
    held = ACCOUNT + "a" * 52
    assert scan.scan({"sha256": held, "file_sha256": held}) == []
    assert scan.scan({"id": "ev:" + ACCOUNT + "a" * 20}) == []
    assert scan.scan({"id": "chg:20261106T141802.457839Z:" + ACCOUNT + "abcd"}) == []
    assert scan.scan({"id": "chg:planted:" + ACCOUNT}) != []


@pytest.mark.parametrize(
    ("value", "category"),
    [
        ("ACCT_DEADBEEF", scan.DIGEST),
        ("acctdeadbeef", scan.DIGEST),
        ("HTTPS://ABC.LAMBDA-URL.EU-NORTH-1.ON.AWS/", scan.FUNCTION_URL),
        ("https%3A%2F%2Fabc%2Elambda%2Durl%2Eeu-north-1%2Eon%2Eaws", scan.FUNCTION_URL),
        ("https%253A%252F%252Fabc%252Elambda-url%252Eeu", scan.FUNCTION_URL),
        ("ABC.EXECUTE-API.EU-NORTH-1.AMAZONAWS.COM", scan.FUNCTION_URL),
        ("a%40example.com", scan.EMAIL),
        ("a＠example.com", scan.EMAIL),
        ("a@example.com-x", scan.EMAIL),
        ("a@example.com2", scan.EMAIL),
        ("a@münchen.de", scan.EMAIL),
        ("verity-canary-7f3a", scan.CANARY),
        ("ARN:AWS:IAM::000000000000:USER/SOMEONE", scan.IDENTITY),
        ("arn:aws:sts::000000000000:assumed-role/some-role/someone", scan.IDENTITY),
        ("C:\\Users\\someone", scan.IDENTITY),
        ("/root/x", scan.IDENTITY),
        ("/private/tmp/x", scan.IDENTITY),
        ("AKIAIOSFODNN7EXAMPLE", scan.AWS_KEY_ID),
        ("AROAIOSFODNN7EXAMPLE", scan.AWS_KEY_ID),
    ],
)
def test_a_value_cannot_pass_by_its_spelling(value, category):
    assert category in {h.category for h in scan.scan({"k": value})}


@pytest.mark.parametrize(
    "value", ["crawler@0.1.0", "cli@1.2.3", "2026-11-06T14:18:02.457839+00:00"]
)
def test_what_the_file_really_holds_still_passes(value):
    assert scan.scan({"k": value}) == []


def test_a_repeated_key_is_refused_because_the_file_still_holds_the_first_value():
    hits = scan.scan_text('{"a":"123456789012","a":"clean"}')
    assert [h.category for h in hits] == [scan.INVALID]


def test_a_constant_that_is_not_json_is_refused():
    assert [h.category for h in scan.scan_text('{"a":NaN}')] == [scan.INVALID]


@pytest.mark.parametrize("form", ["upper", "prefix", "embedded"])
def test_a_replaced_hash_is_found_in_part_and_in_another_case(form):
    old = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0"
    text = {"upper": old.upper(), "prefix": old[:16], "embedded": "xx" + old[8:24] + "yy"}[form]
    assert scan.OLD_HASH in {h.category for h in scan.scan({"k": text}, old_hashes={old})}


def test_a_replaced_hash_given_in_another_case_is_still_found():
    old = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c4b5a69788796a5b4c3d2e1f0"
    assert scan.OLD_HASH in {h.category for h in scan.scan({"k": old}, old_hashes={old.upper()})}


def test_a_hash_exemption_does_not_reach_into_a_list():
    assert scan.ACCOUNT_ID in {h.category for h in scan.scan({"sha256": [ACCOUNT + "a" * 52]})}


def test_the_fixture_scans_clean_with_every_rule():
    built = built_fixture()
    text = serialise(built.snapshot)
    assert scan.scan_text(text, old_hashes=built.redacted.replaced_hashes) == []


# --- finding 3: free-form content and tags are listed ------------------------------------


def test_a_tag_that_is_not_listed_is_left_out_of_the_resource_and_its_evidence():
    content = function_config(OWN)
    content["config"]["tags"] = {"owner": PERSON, "project": "kestrel-demo"}
    graph, made = small_graph(content)
    add(graph, resource(tags={"owner": PERSON, "project": "kestrel-demo"}))
    built = built_from(graph)
    text = serialise(built.snapshot)
    assert PERSON not in text and "owner" not in text and "kestrel-demo" in text
    assert built.report.tags_withheld == 1
    item = next(n for n in document(built)["nodes"] if n["type"] == "Evidence")
    assert item["content"]["config"]["tags"] == {"project": "kestrel-demo"}
    assert item["sha256"] == content_sha256(item["content"])


@pytest.mark.parametrize(
    "content",
    [
        {"brand_new_key": PERSON},
        {"config": {"new_config_key": PERSON}},
        {"config": {"policies": [{"new_policy_key": PERSON}]}},
        {"config": {"policies": [{"statements": [{"new_statement_key": PERSON}]}]}},
        {"config": {"trust": [{"new_trust_key": PERSON}]}},
    ],
)
def test_a_content_key_that_is_not_listed_refuses_the_export_and_names_no_value(content):
    graph, _ = small_graph(content)
    with pytest.raises(RedactionError) as refused:
        built_from(graph)
    assert PERSON not in str(refused.value) and "new_" not in str(refused.value)


def test_a_key_the_crawler_writes_fails_here_and_not_at_the_first_live_export():
    """The fixture runs real function, role and table configs through the listed-key check."""
    resources = {
        (record.content or {}).get("config", {}).get("name") or "function or role"
        for node in fixture_graph().nodes.values()
        if isinstance(record := node["record"], Evidence)
        and record.kind is EvidenceKind.CONFIG_SNAPSHOT
    }
    assert len(resources) > 1
    assert built_fixture().report.evidence_rebuilt > 0


def test_every_key_in_the_fixtures_evidence_is_listed():
    for node in fixture_graph().nodes.values():
        record = node["record"]
        if isinstance(record, Evidence) and record.content:
            listed = PUBLIC_CONTENT_KEYS[record.kind] | WITHHELD_CONTENT_KEYS
            assert set(record.content) <= listed


# --- finding 4: a published hash is always true ------------------------------------------


def test_content_that_names_a_rebuilt_evidence_id_is_refused_not_published_with_a_false_hash():
    graph, made = small_graph(function_config(OWN))
    resource_id, item = made[0]
    later = evidence(resource_id, {"ai_actions": [item.id]}, at=AS_OF + timedelta(hours=1))
    add(graph, later)
    with pytest.raises(RedactionError, match="does not match its content"):
        built_from(graph)


def test_a_record_that_names_a_rebuilt_evidence_id_follows_it():
    graph, made = small_graph(function_config(OWN))
    old = made[0][1].id
    add(graph, Risk(id="risk:planted", title="t", description=f"see {old}", **COMMON))
    built = built_from(graph)
    risk = next(n for n in document(built)["nodes"] if n["id"] == "risk:planted")
    assert risk["description"] == f"see {built.redacted.evidence_ids[old]}"


def test_evidence_whose_only_change_is_its_subject_is_rebuilt():
    subject = f"res:lambda:{OWN}"
    graph, _ = small_graph(function_config(OWN))
    item = evidence(subject, {"statement_count": 1})
    add(graph, resource(id=subject), item)
    built = built_from(graph)
    assert item.id in built.redacted.evidence_ids
    new_id = built.redacted.evidence_ids[item.id]
    published = next(n for n in document(built)["nodes"] if n["id"] == new_id)
    assert published["subject"] == f"res:lambda:{OWN_ACCOUNT}" and published["redacted"] is True


def test_a_file_evidence_with_a_rebuilt_id_keeps_its_file_hash_and_scans_clean(tmp_path):
    subject = f"res:lambda:{OWN}"
    graph, _ = small_graph(function_config(OWN))
    item = Evidence.build(
        subject=subject,
        collector="crawler@0.1.0",
        collected_at=AS_OF,
        content_ref="evidence/file.pdf",
        file_sha256="c" * 64,
        kind=EvidenceKind.DOCUMENT_REF,
        valid_until=AS_OF + timedelta(days=1),
        **COMMON,
    )
    add(graph, resource(id=subject), item)
    built = built_from(graph)
    new_id = built.redacted.evidence_ids[item.id]
    published = next(n for n in document(built)["nodes"] if n["id"] == new_id)
    assert published["sha256"] == "c" * 64 and new_id != item.id
    write_snapshot(tmp_path / "snapshot.json", built)


def test_config_hashes_are_handed_to_the_scanner_even_though_none_is_published():
    graph, _ = small_graph(function_config(OWN))
    add(
        graph,
        ChangeEvent(
            id="chg:planted",
            detected_at=AS_OF,
            previous_config_hash="d" * 64,
            new_config_hash="e" * 64,
            **COMMON,
        ),
    )
    replaced = built_from(graph).redacted.replaced_hashes
    assert {"a" * 64, "b" * 64, "d" * 64, "e" * 64} <= replaced


# --- finding 5: the owner's account ------------------------------------------------------


def test_two_accounts_in_function_roles_are_refused_not_guessed_between():
    graph, _ = small_graph(function_config(OTHER), function_config(OWN))
    with pytest.raises(RedactionError, match="more than one account"):
        built_from(graph)


def test_a_live_graph_with_no_owner_account_is_refused():
    graph, _ = small_graph({"statement_count": 1})
    from unittest.mock import patch

    from export_support import NOTHING

    with (
        patch("verity_core.export.build.estimate_apply", return_value=NOTHING),
        pytest.raises(ValueError, match="owner's account"),
    ):
        build_snapshot(graph, content=LOADED, as_of=AS_OF, data_source="live")


def test_the_same_graph_always_gives_the_same_ordinals():
    extra = {"ai_actions": [f"arn:aws:iam::{OTHER}:root"]}
    graph, _ = small_graph(function_config(OWN), extra)
    assert serialise(built_from(graph).snapshot) == serialise(built_from(graph).snapshot)


# --- finding 6: provenance ---------------------------------------------------------------


def test_the_header_names_everything_that_is_not_real():
    listed = " ".join(document(built_fixture())["header"]["simulated_components"])
    assert "provider: Bedrock (simulated)" in listed and "provider: OpenAI (simulated)" in listed
    assert "simulated sign-offs" in listed
    assert "synthetic records" in listed and "simulated records" in listed


def test_sign_offs_are_named_only_when_a_sign_off_is_simulated():
    graph, _ = small_graph(function_config(OWN))
    assert (
        "simulated sign-offs" not in document(built_from(graph))["header"]["simulated_components"]
    )


def test_a_simulated_snapshot_of_config_is_not_called_a_sign_off():
    graph, _ = small_graph(function_config(OWN))
    item = next(
        graph.nodes[n]["record"]
        for n in graph.nodes
        if isinstance(graph.nodes[n]["record"], Evidence)
    )
    graph.nodes[item.id]["record"] = item.model_copy(update={"source": Source.SIMULATED})
    header = document(built_from(graph))["header"]
    assert "simulated sign-offs" not in header["simulated_components"]
    assert "1 simulated records" in header["simulated_components"]


def test_a_finding_about_a_simulated_result_says_so():
    data = document(built_fixture())
    simulated = {
        (r["control_id"], r["scope_id"]) for r in data["control_results"] if r["simulated"]
    }
    assert simulated
    for finding in data["findings"]:
        assert finding["simulated"] == ((finding["control_id"], finding["subject"]) in simulated)
    assert any(f["simulated"] for f in data["findings"])


# --- the rest ----------------------------------------------------------------------------


def test_every_field_is_required_because_every_field_is_written():
    schema = Snapshot.model_json_schema(mode="serialization")
    evidence_def = schema["$defs"]["SnapshotEvidence"]
    assert "redacted" in evidence_def["required"] and "valid_to" in evidence_def["required"]


def test_records_are_sorted_in_the_file_whatever_the_new_ids_are():
    data = document(built_fixture())
    ids = [n["id"] for n in data["nodes"]]
    assert ids == sorted(ids)
    keys = [(e["src"], e["type"], e["dst"]) for e in data["edges"]]
    assert keys == sorted(keys)


def test_an_edge_goes_through_the_account_map():
    graph, _ = small_graph(function_config(OWN))
    src, dst = f"res:lambda:{OWN}", "res:lambda:other"
    add(graph, resource(id=src), resource(id=dst))
    graph.add_edge(src, dst, record=PlainEdge(src=src, dst=dst, type=EdgeType.ABOUT, **COMMON))
    data = document(built_from(graph))
    assert any(e["src"] == f"res:lambda:{OWN_ACCOUNT}" for e in data["edges"])


def test_a_key_goes_through_the_account_map():
    graph, _ = small_graph(function_config(OWN))
    add(
        graph,
        DiscoveryRun(
            id="run:planted",
            mode="full",
            started_at=AS_OF,
            crawler_version="1",
            summary={OWN: 1},
            **COMMON,
        ),
    )
    run = next(n for n in document(built_from(graph))["nodes"] if n["id"] == "run:planted")
    assert run["summary"] == {OWN_ACCOUNT: 1}


def test_two_records_that_become_one_id_are_refused():
    graph, _ = small_graph(function_config(OWN))
    add(graph, resource(id=f"res:lambda:{OWN}"), resource(id=f"res:lambda:{OWN_ACCOUNT}"))
    with pytest.raises(RedactionError, match="share an ID"):
        built_from(graph)


def write_fixture(tmp_path):
    path = tmp_path / "snapshot.json"
    write_snapshot(path, built_fixture())
    return path


def test_check_refuses_a_field_that_is_not_public(tmp_path, capsys):
    path = write_fixture(tmp_path)
    data = json.loads(path.read_text())
    next(n for n in data["nodes"] if n["type"] == "AWSResource")["unlisted"] = PERSON
    path.write_text(json.dumps(data))
    assert cli.run(["export", "--check", str(path)]) == cli.FAILED
    captured = capsys.readouterr()
    assert PERSON not in captured.err + captured.out


def test_check_can_require_a_live_snapshot(tmp_path, capsys):
    path = write_fixture(tmp_path)
    assert cli.run(["export", "--check", str(path)]) == cli.OK
    assert cli.run(["export", "--check", str(path), "--require-live"]) == cli.FAILED
    data = json.loads(path.read_text())
    data["header"]["data_source"] = "live"
    path.write_text(json.dumps(data))
    assert cli.run(["export", "--check", str(path), "--require-live"]) == cli.OK


# --- what the mutation run showed the suite would not notice -----------------------------


@pytest.mark.parametrize(
    "value",
    ["abc.lambda-url.example", "abc.on.aws", "abc.execute-api.example"],
)
def test_each_url_rule_works_alone(value):
    assert [h.category for h in scan.scan({"k": value})] == [scan.FUNCTION_URL]


def test_the_word_after_an_address_does_not_hide_it():
    assert scan.EMAIL in {h.category for h in scan.scan({"k": "write to a@example.com today"})}


def test_writing_passes_the_replaced_hashes_to_the_scanner(tmp_path):
    graph, made = small_graph(function_config(OWN))
    old = made[0][1].id
    add(graph, Risk(id="risk:planted", title="t", description=f"see {old[3:]}", **COMMON))
    built = built_from(graph)
    with pytest.raises(ScanRejected) as rejected:
        write_snapshot(tmp_path / "snapshot.json", built)
    assert scan.OLD_HASH in {h.category for h in rejected.value.hits}


def test_keys_are_sorted_in_the_file():
    text = serialise(built_fixture().snapshot)
    data = json.loads(text)
    assert list(data) == sorted(data)
    assert list(data["nodes"][0]) == sorted(data["nodes"][0])


def test_a_status_resting_on_a_simulated_sign_off_says_so():
    data = document(built_fixture())
    assert any(s["simulated"] for s in data["requirement_statuses"])


def test_obligations_carry_their_evidence():
    data = document(built_fixture())
    assert any(o["evidence_ids"] for o in data["obligations"])
