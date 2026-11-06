"""Redaction (ADR 0029, decisions 4 to 6): accounts, hashes, rebuilt Evidence and the ID map."""

import json

import pytest
from export_support import (
    AS_OF,
    OTHER,
    OWN,
    THIRD,
    built_from,
    fixture_graph,
    function_config,
    small_graph,
)
from verity_core.export import scan
from verity_core.export.build import serialise
from verity_core.export.redact import OWN_ACCOUNT, RedactionError, redact
from verity_core.model.evidence import content_sha256, evidence_id


def evidence_nodes(built):
    return [n for n in built.snapshot.model_dump(mode="json")["nodes"] if n["type"] == "Evidence"]


def text_of(built) -> str:
    return serialise(built.snapshot)


# --- accounts ----------------------------------------------------------------------------


def test_the_own_account_becomes_000000000000():
    graph, _ = small_graph(function_config(OWN, f"arn:aws:logs:eu-north-1:{OWN}:log-group:x"))
    text = text_of(built_from(graph))
    assert OWN not in text
    assert f"arn:aws:iam::{OWN_ACCOUNT}:role/some-role" in text
    assert f"arn:aws:logs:eu-north-1:{OWN_ACCOUNT}:log-group:x" in text


def test_an_external_account_gets_an_ordinal_in_order_of_first_appearance():
    graph, _ = small_graph(
        function_config(OWN, f"arn:aws:iam::{THIRD}:role/b", f"arn:aws:iam::{OTHER}:root"),
        function_config(OWN, f"arn:aws:iam::{OTHER}:role/c"),
    )
    built = built_from(graph)
    text = text_of(built)
    assert OTHER not in text and THIRD not in text and OWN not in text
    # The records are walked in sorted order, and within a record in sorted key order, so
    # `resources` lists THIRD first. Both appear, as ordinals.
    assert "acct_1" in text and "acct_2" in text and "acct_3" not in text
    assert built.report.external_accounts == 2
    assert built.report.own_account_found is True


def test_the_same_graph_always_gives_the_same_ordinals():
    contents = (function_config(OWN, f"arn:aws:iam::{THIRD}:r", f"arn:aws:iam::{OTHER}:r"),)
    first = text_of(built_from(small_graph(*contents)[0]))
    second = text_of(built_from(small_graph(*contents)[0]))
    assert first == second


def test_with_no_own_account_found_every_account_is_an_ordinal():
    graph, _ = small_graph({"note": f"see arn:aws:iam::{OTHER}:root"})
    built = built_from(graph)
    text = text_of(built)
    assert OTHER not in text and "acct_1" in text and OWN_ACCOUNT not in text
    assert built.report.own_account_found is False


# --- hashes ------------------------------------------------------------------------------


def test_the_config_hash_keys_are_withheld_at_every_depth_inside_evidence():
    nested = {
        "a": {"config_hash": "x"},
        "b": [{"previous_config_hash": "y"}],
        "new_config_hash": "z",
    }
    graph, _ = small_graph({**nested, "kept": 1})
    built = built_from(graph)
    (item,) = evidence_nodes(built)
    assert item["content"] == {"a": {}, "b": [{}], "kept": 1}
    assert built.report.content_keys_withheld == 3
    assert "config_hash" not in text_of(built)


def test_a_resources_config_hash_field_is_not_published():
    graph, _ = small_graph({"k": 1})
    resource = next(
        n for n in built_from(graph).snapshot.model_dump()["nodes"] if n["type"] == "AWSResource"
    )
    assert "config_hash" not in resource


def test_changed_evidence_is_rebuilt_with_a_new_hash_and_id_and_is_marked():
    graph, made = small_graph(function_config(OWN))
    ((_, original),) = made
    built = built_from(graph)
    (item,) = evidence_nodes(built)
    assert item["redacted"] is True
    assert item["sha256"] != original.sha256 and item["id"] != original.id
    assert item["sha256"] == content_sha256(item["content"])
    from datetime import datetime

    collected = datetime.fromisoformat(item["collected_at"])
    assert item["id"] == evidence_id(item["subject"], item["collector"], collected, item["sha256"])


def test_no_old_hash_or_id_of_redacted_evidence_survives_in_the_output():
    graph, made = small_graph(function_config(OWN), function_config(OWN, "x"))
    built = built_from(graph)
    text = text_of(built)
    for _, original in made:
        assert original.id not in text and original.sha256 not in text
    assert built.redacted.replaced_hashes == {value for _, o in made for value in (o.id, o.sha256)}
    assert scan.scan_text(text, old_hashes=built.redacted.replaced_hashes) == []


def test_unchanged_evidence_keeps_its_hash_and_id():
    graph, made = small_graph({"plain": "content", "n": 1})
    ((_, original),) = made
    built = built_from(graph)
    (item,) = evidence_nodes(built)
    assert (item["id"], item["sha256"], item["redacted"]) == (original.id, original.sha256, False)
    assert built.report.evidence_unchanged == 1 and built.report.evidence_rebuilt == 0
    assert built.redacted.replaced_hashes == frozenset()


def test_two_items_that_become_identical_are_refused():
    same = AS_OF
    from export_support import COMMON, evidence
    from verity_core.graph.memory import InMemoryRepository
    from verity_core.model import ids
    from verity_core.model.enums import NodeType
    from verity_core.model.nodes import AWSResource

    repo = InMemoryRepository("kestrel", lambda: AS_OF)
    resource = ids.make_id(NodeType.AWS_RESOURCE, "lambda", "fn")
    repo.upsert_node(
        AWSResource(id=resource, resource_type="lambda", region="eu-north-1", name="fn", **COMMON)
    )
    # Different before redaction, identical after: only the withheld hash differs.
    for value in ("a" * 64, "b" * 64):
        repo.upsert_node(
            evidence(resource, {"config": {"role": "x"}, "config_hash": value}, at=same)
        )
    with pytest.raises(RedactionError, match="identical"):
        redact(repo.load_graph())


# --- references --------------------------------------------------------------------------


def test_every_edge_and_reference_resolves_after_the_id_map():
    graph, made = small_graph(function_config(OWN), function_config(OWN, "y"))
    data = built_from(graph).snapshot.model_dump(mode="json")
    ids_ = {n["id"] for n in data["nodes"]}
    assert all(e["src"] in ids_ and e["dst"] in ids_ for e in data["edges"])
    assert all(n["subject"] in ids_ for n in data["nodes"] if n["type"] == "Evidence")
    old = {o.id for _, o in made}
    assert not (old & ids_)  # the edges followed the map: SUPPORTS and ABOUT now name the new IDs
    supports = [e for e in data["edges"] if e["type"] == "SUPPORTS"]
    assert {e["src"] for e in supports} == {
        n["id"] for n in data["nodes"] if n["type"] == "Evidence"
    }


def test_every_reference_resolves_in_the_full_fixture_snapshot():
    data = built_from(fixture_graph()).snapshot.model_dump(mode="json")
    ids_ = {n["id"] for n in data["nodes"]}
    assert len(ids_) == len(data["nodes"])
    assert all(e["src"] in ids_ and e["dst"] in ids_ for e in data["edges"])
    assert all(n["subject"] in ids_ for n in data["nodes"] if n["type"] == "Evidence")
    assert all(
        n["assessor"] in ids_
        for n in data["nodes"]
        if n["type"] == "ControlAssessment" and n["assessor"]
    )


def test_an_edge_still_naming_an_old_id_is_refused(monkeypatch):
    """If the ID map were not applied to the edges, they would point at nothing."""
    import re

    from verity_core.export import redact as module

    graph, _ = small_graph(function_config(OWN))
    monkeypatch.setattr(module, "_EVIDENCE_ID", re.compile("(?!)"))  # matches nothing
    with pytest.raises(RedactionError, match="no endpoint"):
        redact(graph)


def test_a_reference_that_resolved_before_and_not_after_is_refused():
    from verity_core.export.redact import _references

    before = [
        {"id": "res:lambda:a", "type": "AWSResource"},
        {"id": "ev:" + "1" * 32, "type": "Evidence", "subject": "res:lambda:a"},
    ]
    after = [before[0], {**before[1], "subject": "res:lambda:gone"}]
    assert _references(before) == {"1#subject": True}
    assert _references(after) == {"1#subject": False}


# --- the whole fixture -------------------------------------------------------------------


def test_the_fixture_snapshot_passes_the_scan_and_holds_no_canary_or_hash_key():
    built = built_from(fixture_graph())
    text = text_of(built)
    assert scan.scan_text(text, old_hashes=built.redacted.replaced_hashes) == []
    assert "CANARY" not in text and "config_hash" not in text
    assert built.report.evidence_rebuilt > 0 and built.report.own_account_found


def test_the_d1_canary_on_every_env_var_never_reaches_the_file():
    """The fixture sets the canary text as the value of every env var (D1). The graph holds the
    names only, so the file does too."""
    raw = json.loads((__import__("export_support").FIXTURE).read_text())
    values = {
        v for f in raw["functions"] for v in f.get("Environment", {}).get("Variables", {}).values()
    }
    assert values == {"VERITY-CANARY-7f3a"}
    text = text_of(built_from(fixture_graph()))
    assert "7f3a" not in text and "VERITY-CANARY" not in text
    names = {n for f in raw["functions"] for n in f.get("Environment", {}).get("Variables", {})}
    published = {
        name
        for node in json.loads(text)["nodes"]
        if node["type"] == "AWSResource"
        for name in node["env_var_names"]
    }
    assert names <= published


def test_every_published_redacted_hash_verifies_against_the_published_content():
    for item in evidence_nodes(built_from(fixture_graph())):
        if item["content"] is None:
            continue
        assert item["sha256"] == content_sha256(item["content"]), item["id"]
