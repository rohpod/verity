"""Capability without usage: the crawler's VC-060 check, assessed against the real content.

These run on the in-memory repository only: seeding and assessing the real content writes about
1,800 records, which takes minutes on the moto table. The crawler's own writes, including the
VC-060 evidence, are covered on both backends in `test_pipeline.py`.
"""

from uuid import uuid4

import pytest
from discovery_support import (
    CANARY,
    CONTENT_LOADED,
    crawl_fixture,
    dump,
    edited_fixture,
    of_type,
    seeded,
    trail_event_json,
)
from verity_core.assess.apply import apply_assessment
from verity_core.assess.requirements import RequirementState
from verity_core.graph.memory import InMemoryRepository
from verity_core.model.enums import (
    AssuranceLevel,
    EvidenceKind,
    ImplementationStatus,
    NodeType,
    Source,
)
from verity_core.model.usage import UsageRecord

SYSTEM = "sys:support-assistant"
CONTROL = "ctl:VC-060"


def assess(repo, clock):
    clock.advance(minutes=5)
    return apply_assessment(repo, CONTENT_LOADED.rules, CONTENT_LOADED.dates, clock.now, clock)


def result(outcome, scope=SYSTEM):
    return next(r for r in outcome.results if (r.control_id, r.scope_id) == (CONTROL, scope))


def vc060_evidence(repo, scope=SYSTEM):
    return [
        e
        for e in of_type(repo, NodeType.EVIDENCE)
        if e.kind is EvidenceKind.AUTOMATED_TEST and e.subject == scope
    ]


@pytest.fixture
def repo(clock):
    return InMemoryRepository("kestrel", clock)


@pytest.fixture
def crawled(repo, clock):
    seeded(repo, clock, CONTENT_LOADED)
    crawl_fixture(repo, clock, content=CONTENT_LOADED)
    return repo


def test_an_unused_bedrock_grant_is_not_implemented_at_l3_and_a_high_finding(crawled, clock):
    outcome = assess(crawled, clock)
    row = result(outcome)
    assert (row.status, row.level) == (
        ImplementationStatus.NOT_IMPLEMENTED,
        AssuranceLevel.L3_TESTED,
    )
    assert row.method == "automated_test_fail"
    (evidence,) = vc060_evidence(crawled)
    assert evidence.content["unused"] == ["bedrock:InvokeModel"]
    assert evidence.content["granted"] == ["bedrock:InvokeModel"]
    assert evidence.source is Source.SIMULATED and row.source is Source.SIMULATED
    assert CANARY not in dump(crawled)  # nor anything the assessment stored
    high = [f for f in outcome.findings if f.code == "control_not_met" and f.subject == SYSTEM]
    assert [(f.severity.value, CONTROL in f.message) for f in high] == [("high", True)]


def test_systems_without_an_ai_grant_pass(crawled, clock):
    outcome = assess(crawled, clock)
    for scope in ("sys:talent-screening", "sys:contract-insights"):
        row = result(outcome, scope)
        assert (row.status, row.level) == (
            ImplementationStatus.IMPLEMENTED,
            AssuranceLevel.L3_TESTED,
        )


def test_usage_records_do_not_hide_the_finding(repo, clock):
    seeded(repo, clock, CONTENT_LOADED)
    repo.append_usage(
        UsageRecord(
            tenant=CONTENT_LOADED.tenant,
            usage_id=uuid4(),
            system_id=SYSTEM,
            provider_id="prov:mock-bedrock",
            model_id="model:bedrock-fm",
            timestamp=clock.now,
            token_estimate=10,
            source=Source.SIMULATED,
        )
    )
    clock.advance(minutes=1)
    report = crawl_fixture(repo, clock, content=CONTENT_LOADED)
    scored = {name: (level, signals) for name, level, signals in report.functions}
    assert "usage_records" in scored["support-assistant"][1]
    assert result(assess(repo, clock)).status is ImplementationStatus.NOT_IMPLEMENTED


def test_a_matching_trail_event_passes_but_never_makes_a_requirement_satisfied(
    repo, clock, tmp_path
):
    seeded(repo, clock, CONTENT_LOADED)

    def used(raw):
        raw["trail_events"].append(trail_event_json("support-assistant-role"))

    report = crawl_fixture(repo, clock, edited_fixture(tmp_path, used), CONTENT_LOADED)
    scored = {name: (level, signals) for name, level, signals in report.functions}
    assert "trail_ai_event" in scored["support-assistant"][1]
    outcome = assess(repo, clock)
    row = result(outcome)
    assert (row.status, row.level) == (ImplementationStatus.IMPLEMENTED, AssuranceLevel.L3_TESTED)
    assert not [f for f in outcome.findings if f.code == "control_not_met" and f.subject == SYSTEM]
    a82 = next(
        s
        for s in outcome.statuses
        if s.system_id == SYSTEM and s.requirement_id == "req:iso27001:A.8.2"
    )
    assert a82.state is not RequirementState.SATISFIED  # automated checks alone never make one


def test_a_not_action_role_is_a_broad_grant_and_fails(repo, clock, tmp_path):
    seeded(repo, clock, CONTENT_LOADED)

    def odd(raw):
        policy = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "NotAction": "iam:*", "Resource": "*"}],
        }
        next(r for r in raw["roles"] if r["role"]["RoleName"] == "talent-screening-role")[
            "inline_policies"
        ].append({"PolicyName": "odd", "PolicyDocument": policy})

    crawl_fixture(repo, clock, edited_fixture(tmp_path, odd), CONTENT_LOADED)
    (evidence,) = vc060_evidence(repo, "sys:talent-screening")
    assert evidence.content["outcome"] == "fail" and len(evidence.content["granted"]) == 8


def test_the_check_is_written_again_only_when_its_content_or_sources_change(repo, clock, tmp_path):
    seeded(repo, clock, CONTENT_LOADED)
    crawl_fixture(repo, clock, content=CONTENT_LOADED)
    clock.advance(hours=1)
    quiet = crawl_fixture(repo, clock, content=CONTENT_LOADED)
    assert quiet.summary["evidence_written"] == 0
    assert len(vc060_evidence(repo)) == 1

    clock.advance(hours=1)

    def used(raw):
        raw["trail_events"].append(trail_event_json("support-assistant-role"))

    crawl_fixture(repo, clock, edited_fixture(tmp_path, used), CONTENT_LOADED)
    assert sorted(e.content["outcome"] for e in vc060_evidence(repo)) == ["fail", "pass"]


def test_a_change_to_the_function_alone_makes_the_check_fresh_again(repo, clock, tmp_path):
    seeded(repo, clock, CONTENT_LOADED)
    crawl_fixture(repo, clock, content=CONTENT_LOADED)
    clock.advance(hours=1)

    def tweak(raw):
        raw["functions"][0]["MemorySize"] = 256

    crawl_fixture(repo, clock, edited_fixture(tmp_path, tweak), CONTENT_LOADED)
    evidence = vc060_evidence(repo)
    assert len(evidence) == 2 and evidence[0].content == evidence[1].content
    outcome = assess(repo, clock)
    assert result(outcome).evidence_id == max(evidence, key=lambda e: e.collected_at).id
    assert result(outcome).status is ImplementationStatus.NOT_IMPLEMENTED


def test_an_unseen_role_is_inconclusive_and_replaces_an_older_pass(repo, clock, tmp_path):
    seeded(repo, clock, CONTENT_LOADED)
    crawl_fixture(repo, clock, content=CONTENT_LOADED)
    first = assess(repo, clock)
    assert result(first, "sys:talent-screening").status is ImplementationStatus.IMPLEMENTED

    def hide(raw):
        raw["roles"] = [r for r in raw["roles"] if r["role"]["RoleName"] != "talent-screening-role"]

    clock.advance(hours=1)
    crawl_fixture(repo, clock, edited_fixture(tmp_path, hide), CONTENT_LOADED)
    (_, latest) = sorted(vc060_evidence(repo, "sys:talent-screening"), key=lambda e: e.collected_at)
    assert latest.content["outcome"] == "inconclusive" and latest.content["roles_unseen"] == 1
    row = result(assess(repo, clock), "sys:talent-screening")
    assert (row.status, row.level) == (
        ImplementationStatus.NOT_ASSESSED,
        AssuranceLevel.L0_INFERRED,
    )


def test_a_list_call_from_the_role_neither_scores_as_usage_nor_proves_the_grant(
    repo, clock, tmp_path
):
    seeded(repo, clock, CONTENT_LOADED)

    def listed(raw):
        raw["trail_events"].append(
            trail_event_json("support-assistant-role", name="ListFoundationModels")
        )

    report = crawl_fixture(repo, clock, edited_fixture(tmp_path, listed), CONTENT_LOADED)
    scored = {name: signals for name, _, signals in report.functions}
    assert "trail_ai_event" not in scored["support-assistant"]
    assert result(assess(repo, clock)).status is not ImplementationStatus.IMPLEMENTED


def test_converse_in_cloudtrail_proves_the_seeded_invoke_model_grant(repo, clock, tmp_path):
    seeded(repo, clock, CONTENT_LOADED)

    def used(raw):
        raw["trail_events"].append(trail_event_json("support-assistant-role", name="Converse"))

    crawl_fixture(repo, clock, edited_fixture(tmp_path, used), CONTENT_LOADED)
    assert result(assess(repo, clock)).status is ImplementationStatus.IMPLEMENTED
