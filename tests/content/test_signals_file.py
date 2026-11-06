import copy
import json
from pathlib import Path

import pytest
from content_samples import at_scale, good_files, write_tree
from verity_core.content.lint import lint
from verity_core.content.loader import ContentError, load_content

ROOT = Path(__file__).parents[2] / "content"
CONTENT = load_content(ROOT)


def signals(**changes) -> dict:
    base = {
        "evidence_valid_days": 30,
        "evidence_refresh_days": 8,
        "trail_lookback_days": 90,
        "trail_event_sources": ["bedrock.amazonaws.com"],
        "platform_tag": "verity:component",
        "platform_functions": ["mock-openai"],
        "ai_actions": [{"action": "bedrock:InvokeModel", "trail_events": ["Converse"]}],
        "signals": [
            {"id": "tag_system_id", "kind": "tag", "key": "ai:system-id", "likelihood": "declared"},
            {"id": "env", "kind": "env_name", "likelihood": "probable", "pattern": "^OPENAI_"},
        ],
    }
    return base | changes


def load(tmp_path, file: dict):
    files = copy.deepcopy(good_files())
    at_scale(files)
    files["rules/ai_signals.yaml"] = file
    return load_content(write_tree(tmp_path, files))


def codes(content) -> set[str]:
    return {i.code for i in lint(content)}


def test_the_real_signals_load_and_lint_clean():
    assert CONTENT.signals is not None
    assert [i for i in lint(CONTENT) if i.subject.startswith("signal")] == []
    assert {s.kind for s in CONTENT.signals.signals} == {
        "tag",
        "manifest",
        "usage_record",
        "trail_event",
        "iam_action",
        "env_name",
        "name",
    }


def test_content_without_a_signals_file_still_loads(tmp_path):
    files = copy.deepcopy(good_files())
    at_scale(files)
    assert load_content(write_tree(tmp_path, files)).signals is None


def test_a_good_file_loads_and_lints_clean(tmp_path):
    assert codes(load(tmp_path, signals())) == set()


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "t", "kind": "tag", "likelihood": "declared"},  # a tag needs a key
        {"id": "t", "kind": "manifest", "likelihood": "declared", "key": "x"},
        {"id": "t", "kind": "env_name", "likelihood": "probable"},  # needs a pattern
        {"id": "t", "kind": "manifest", "likelihood": "none"},  # a signal that fires scores
        {"id": "t", "kind": "guess", "likelihood": "possible"},
    ],
)
def test_a_malformed_signal_cannot_be_read(tmp_path, bad):
    with pytest.raises(ContentError):
        load(tmp_path, signals(signals=[bad]))


def test_refresh_must_be_inside_the_validity(tmp_path):
    with pytest.raises(ContentError):
        load(tmp_path, signals(evidence_refresh_days=30))


def test_lint_refuses_a_duplicate_id(tmp_path):
    rule = {"id": "same", "kind": "manifest", "likelihood": "declared"}
    other = {"id": "same", "kind": "iam_action", "likelihood": "probable"}
    assert "signal_duplicate_id" in codes(load(tmp_path, signals(signals=[rule, other])))


def test_lint_refuses_an_id_the_crawler_uses(tmp_path):
    rule = {"id": "platform_component", "kind": "manifest", "likelihood": "declared"}
    assert "signal_reserved_id" in codes(load(tmp_path, signals(signals=[rule])))


def test_lint_refuses_a_pattern_that_does_not_compile(tmp_path):
    rule = {"id": "env", "kind": "env_name", "likelihood": "probable", "pattern": "(unclosed"}
    assert "signal_bad_pattern" in codes(load(tmp_path, signals(signals=[rule])))


def test_lint_refuses_a_repeated_trail_source(tmp_path):
    file = signals(trail_event_sources=["bedrock.amazonaws.com"] * 2)
    assert "signal_duplicate_source" in codes(load(tmp_path, file))


def test_the_crawl_fixture_is_the_recorded_estate_of_the_plan():
    estate = json.loads((ROOT / "fixtures" / "crawl" / "estate.json").read_text())
    assert set(estate) == {
        "_comment",
        "functions",
        "tag_mappings",
        "roles",
        "tables",
        "manifests",
        "trail_events",
    }
    assert [f["FunctionName"] for f in estate["functions"]] == [
        "support-assistant",
        "talent-screening",
        "contract-insights",
        "shadow-summariser",
        "invoice-renderer",
        "mock-openai",
    ]
    assert estate["trail_events"] == []


def test_every_env_var_in_the_fixture_holds_the_canary():
    estate = json.loads((ROOT / "fixtures" / "crawl" / "estate.json").read_text())
    values = {
        v
        for f in estate["functions"]
        for v in f.get("Environment", {}).get("Variables", {}).values()
    }
    assert values == {"VERITY-CANARY-7f3a"}


def test_lint_refuses_a_repeated_ai_action(tmp_path):
    action = {"action": "bedrock:InvokeModel"}
    assert "signal_duplicate_action" in codes(load(tmp_path, signals(ai_actions=[action, action])))


def test_an_ai_action_must_be_a_real_action_name_and_not_a_pattern(tmp_path):
    with pytest.raises(ContentError):
        load(tmp_path, signals(ai_actions=[{"action": "bedrock:Invoke*"}]))
