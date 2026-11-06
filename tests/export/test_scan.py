"""The scanner (ADR 0029, decision 7): each category catches a planted value, reports where and
never what, and lets the harmless look-alikes through."""

import ast
import json
from pathlib import Path

import pytest
from verity_core.export import scan
from verity_core.export.scan import Hit, scan_text

# Planted values are built in pieces, so this file holds none of them whole.
ACCOUNT = "1234" + "5678" + "9012"
PLANTED = {
    scan.ACCOUNT_ID: f"arn:aws:iam::{ACCOUNT}:role/x",
    scan.DIGEST: "acct_" + "0a1b2c3d",
    scan.FUNCTION_URL: "https://abc." + "lambda-url.eu-north-1.on." + "aws/",
    scan.EMAIL: "someone" + "@" + "example." + "com",
    scan.CANARY: "VERITY-" + "CANARY-7f3a",
    scan.IDENTITY: "arn:aws:iam::000000000000:" + "user/" + "somebody",
}


@pytest.mark.parametrize("category", sorted(PLANTED))
def test_each_category_catches_a_planted_value_in_a_value(category):
    document = {"nodes": [{"a": {"b": [PLANTED[category]]}}]}
    hits = scan.scan(document)
    assert Hit(category, "$.nodes[0].a.b[0]") in hits


@pytest.mark.parametrize("category", sorted(PLANTED))
def test_each_category_catches_a_planted_value_in_a_key(category):
    hits = scan.scan({"outer": {PLANTED[category]: 1}})
    assert [h.category for h in hits] == [category]
    assert hits[0].path == "$.outer.{key 0}"


@pytest.mark.parametrize("category", sorted(PLANTED))
def test_a_report_names_the_category_and_path_and_never_the_value(category):
    value = PLANTED[category]
    hits = scan.scan({value: {"x": value}, "ok": [value]})
    assert hits
    for hit in hits:
        assert value not in str(hit) and value not in hit.path
        assert ACCOUNT not in str(hit)


def test_a_sensitive_key_is_hidden_in_the_path_of_everything_below_it():
    hits = scan.scan({PLANTED[scan.DIGEST]: {"deep": ACCOUNT}})
    assert {h.path for h in hits} == {"$.{key 0}", "$.{key 0}.deep"}
    assert not [h for h in hits if "0a1b2c3d" in h.path]


def test_a_path_through_ordinary_keys_and_lists_is_readable():
    hits = scan.scan({"nodes": [{}, {"content": {"config": {"role": PLANTED[scan.ACCOUNT_ID]}}}]})
    assert [h.path for h in hits] == ["$.nodes[1].content.config.role"]


def test_the_placeholder_account_passes():
    assert scan.scan({"arn": "arn:aws:iam::000000000000:role/x"}) == []


def test_other_digits_that_are_not_an_account_pass():
    assert (
        scan.scan({"n": "12345678901", "m": "1234567890123", "date": "2026-11-06T12:00:00Z"}) == []
    )


def test_a_number_that_is_twelve_digits_is_an_account():
    assert [h.category for h in scan.scan({"n": int(ACCOUNT)})] == [scan.ACCOUNT_ID]


def test_the_crawler_collector_is_not_an_email():
    assert scan.scan({"collector": "crawler@0.1.0", "other": "cli@1.2.3"}) == []


def test_a_hash_that_holds_twelve_digits_passes():
    digits = "012184748980"
    sha = digits + "ab" * 26
    assert len(sha) == 64 and len(sha) == len(sha.lower())
    assert scan.scan({"sha256": sha, "id": "ev:" + digits + "cd" * 10}) == []


def test_twelve_digits_inside_a_longer_text_are_still_refused():
    assert [h.category for h in scan.scan({"t": "see " + ACCOUNT + " here"})] == [scan.ACCOUNT_ID]


def test_a_bare_hash_with_twelve_digits_is_only_exempt_when_it_is_the_whole_value():
    sha = "012184748980" + "ab" * 26
    assert [h.category for h in scan.scan({"t": "hash " + sha})] == [scan.ACCOUNT_ID]


@pytest.mark.parametrize("text", ["/Users/someone/code", "/home/someone", "at /home/x"])
def test_local_paths_are_refused(text):
    assert [h.category for h in scan.scan({"p": text})] == [scan.IDENTITY]


def test_a_role_arn_is_not_an_identity_but_a_user_arn_is():
    assert scan.scan({"a": "arn:aws:iam::000000000000:role/some-role"}) == []
    assert [h.category for h in scan.scan({"a": PLANTED[scan.IDENTITY]})] == [scan.IDENTITY]


def test_a_replaced_hash_is_refused_anywhere_it_appears():
    old = "ev:" + "9" * 32
    document = {"edges": [{"src": old}], "note": "see " + old + " above"}
    hits = scan.scan(document, old_hashes={old})
    assert [h.category for h in hits] == [scan.OLD_HASH, scan.OLD_HASH]
    assert old not in "".join(str(h) for h in hits)


def test_without_the_graph_old_hashes_cannot_be_tested():
    assert scan.scan({"x": "ev:" + "9" * 32}) == []


def test_text_is_parsed_so_escaped_forms_are_seen_as_read():
    escaped = json.dumps({"k": PLANTED[scan.EMAIL]}, ensure_ascii=True).replace("@", "\\u0040")
    assert "@" not in escaped
    assert [h.category for h in scan_text(escaped)] == [scan.EMAIL]


def test_text_that_is_not_json_is_a_hit():
    assert scan_text("{not json") == [Hit(scan.INVALID, "$")]


def test_booleans_null_and_small_numbers_pass():
    assert scan.scan({"a": True, "b": None, "c": 1.5, "d": -3, "e": [1, 2]}) == []


def test_the_scanner_shares_no_code_with_the_redaction():
    """It imports neither the redaction nor the field lists, so it reuses none of their patterns."""
    source = (Path(__file__).parents[2] / "core/verity_core/export/scan.py").read_text()
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    assert not [m for m in imported if m.startswith("verity_core")], imported
