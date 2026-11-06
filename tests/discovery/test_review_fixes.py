"""Log hygiene, crash repair and the manifest count (ADR 0022, decisions 6, 7, 8 and 10)."""

import logging
from collections import Counter
from contextlib import nullcontext, suppress

from discovery_support import (
    CANARY,
    CONTENT_LOADED,
    aws_collector,
    crawl_fixture,
    edited_fixture,
    of_type,
    populate_moto,
    seeded,
)
from moto import mock_aws
from verity_core.assess.apply import apply_assessment
from verity_core.graph.memory import InMemoryRepository
from verity_core.model.enums import AiLikelihood as L
from verity_core.model.enums import EvidenceKind, NodeType
from verity_core.model.evidence import Evidence
from verity_core.rules.finding import Severity


class Crash(Exception):
    pass


class CrashesOnEvidence:
    """A repository that fails the first time it is asked to write Evidence."""

    def __init__(self, inner):
        self._inner = inner
        self.armed = True

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def upsert_node(self, node):
        if self.armed and isinstance(node, Evidence):
            raise Crash
        return self._inner.upsert_node(node)


GHOST = "system: sys:lead-scoring\nresources:\n  - {type: lambda, name: not-there}\n"


def tweak(raw):
    raw["functions"][0]["MemorySize"] = 256  # support-assistant


def test_aws_library_debug_logs_never_hold_an_env_value(repo, clock, caplog):

    from verity_core.discovery.aws import QUIET_LOGGERS

    context = mock_aws() if isinstance(repo, InMemoryRepository) else nullcontext()
    with context:
        populate_moto()  # the setup requests hold the value, so they come first
        before = {name: logging.getLogger(name).level for name in QUIET_LOGGERS}
        try:
            logging.getLogger().setLevel(logging.DEBUG)
            caplog.set_level(logging.DEBUG)
            caplog.clear()
            aws_collector(clock).collect()
        finally:
            logging.getLogger().setLevel(logging.WARNING)
            for name, level in before.items():
                logging.getLogger(name).setLevel(level)
    assert CANARY not in caplog.text


def test_a_crash_at_the_evidence_step_is_repaired_by_the_next_run(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(hours=1)
    crashing = CrashesOnEvidence(repo)
    try:
        crawl_fixture(crashing, clock, edited_fixture(tmp_path, tweak))
    except Crash:
        pass
    else:
        raise AssertionError("expected the crash")
    assert len(of_type(repo, NodeType.CHANGE_EVENT)) == 1  # written before the node changed

    clock.advance(hours=1)
    retry = crawl_fixture(repo, clock, edited_fixture(tmp_path, tweak))
    assert retry.changes == ()  # the retry sees no change...
    checks = [
        e
        for e in of_type(repo, NodeType.EVIDENCE)
        if e.kind is EvidenceKind.AUTOMATED_TEST and e.subject == "sys:support-assistant"
    ]
    assert len(checks) == 2  # ...and still writes the check again
    assert max(checks, key=lambda e: e.collected_at).collected_at == clock.now

    clock.advance(hours=1)
    assert crawl_fixture(repo, clock, edited_fixture(tmp_path, tweak)).written == Counter(runs=1)


def test_after_a_crash_the_failed_check_is_still_a_high_finding(clock, tmp_path):
    repo = InMemoryRepository("kestrel", clock)
    seeded(repo, clock, CONTENT_LOADED)
    crawl_fixture(repo, clock, content=CONTENT_LOADED)
    clock.advance(hours=1)
    with suppress(Crash):
        crawl_fixture(
            CrashesOnEvidence(repo), clock, edited_fixture(tmp_path, tweak), CONTENT_LOADED
        )
    clock.advance(hours=1)
    crawl_fixture(repo, clock, edited_fixture(tmp_path, tweak), CONTENT_LOADED)
    clock.advance(minutes=5)
    outcome = apply_assessment(repo, CONTENT_LOADED.rules, CONTENT_LOADED.dates, clock.now, clock)
    high = {(f.code, f.subject) for f in outcome.findings if f.severity is Severity.HIGH}
    assert ("control_not_met", "sys:support-assistant") in high
    assert ("no_evidence", "sys:support-assistant") not in {
        (f.code, f.subject) for f in outcome.findings if "VC-060" in f.message
    }


def test_the_platform_tag_hides_only_the_named_platform_functions(repo, clock, tmp_path):
    seeded(repo, clock)

    def tag_shadow(raw):
        arn = next(f["FunctionArn"] for f in raw["functions"] if "shadow" in f["FunctionName"])
        raw["tag_mappings"].append(
            {"ResourceARN": arn, "Tags": [{"Key": "verity:component", "Value": "x"}]}
        )

    report = crawl_fixture(repo, clock, edited_fixture(tmp_path, tag_shadow))
    levels = {n: (level, signals) for n, level, signals in report.functions}
    assert levels["shadow-summariser"][0] is L.PROBABLE
    assert levels["mock-openai"] == (L.NONE, ("platform_component",))
    assert [c.name for c in of_type(repo, NodeType.CANDIDATE)] == ["shadow-summariser"]


def test_an_untagged_mock_is_scored_on_its_signals(repo, clock, tmp_path):
    seeded(repo, clock)

    def untag(raw):
        raw["tag_mappings"] = [
            m for m in raw["tag_mappings"] if "mock-openai" not in m["ResourceARN"]
        ]
        mock = next(f for f in raw["functions"] if f["FunctionName"] == "mock-openai")
        mock["Environment"] = {"Variables": {"OPENAI_BASE_URL": "x"}}

    report = crawl_fixture(repo, clock, edited_fixture(tmp_path, untag))
    levels = {n: level for n, level, _ in report.functions}
    assert levels["mock-openai"] is L.PROBABLE


def test_a_manifest_naming_a_missing_function_is_counted(repo, clock, tmp_path):
    seeded(repo, clock)

    def ghost(raw):
        raw["manifests"].append(
            {
                "Name": "/verity/manifests/ghost.yaml",
                "Value": GHOST,
            }
        )

    report = crawl_fixture(repo, clock, edited_fixture(tmp_path, ghost))
    assert report.summary["manifest_functions_missing"] == 1
    assert crawl_fixture(repo, clock).summary["manifest_functions_missing"] == 0
