"""A crawl followed by an assessment, on both backends. The content is cut down to the one
control and requirement the crawler's evidence reaches, so the moto table stays fast."""

import dataclasses
from datetime import UTC, datetime

from discovery_support import CONTENT, CONTENT_LOADED, MINI, crawl_fixture, of_type, seeded
from verity_core import cli
from verity_core.assess.apply import apply_assessment
from verity_core.content.schema import ApplicabilityFile, ApplicabilityRule
from verity_core.graph.memory import InMemoryRepository
from verity_core.model.enums import Direction, EdgeType, ImplementationStatus, NodeType

REQUIREMENT = "req:iso27001:A.8.2"
SYSTEM = "sys:support-assistant"


def small():
    wanted = {REQUIREMENT, "ctl:VC-060", "fw:iso27001"}
    requirements = tuple(r for r in CONTENT_LOADED.requirements if r.id == REQUIREMENT)
    edges = tuple(
        e
        for e in CONTENT_LOADED.edges
        if {e.src, e.dst} <= wanted and e.type in (EdgeType.MAPS_TO, EdgeType.PART_OF)
    )
    rule = ApplicabilityRule(
        id="adopted", leaves_of=["iso27001"], target="organisation", role="any"
    )
    return dataclasses.replace(
        MINI,
        frameworks=tuple(f for f in CONTENT_LOADED.frameworks if f.id == "fw:iso27001"),
        requirements=requirements,
        controls=tuple(c for c in CONTENT_LOADED.controls if c.id == "ctl:VC-060"),
        edges=edges,
        rules=ApplicabilityFile(annex_iii_domains={}, rules=[rule]),
    )


def test_a_crawl_then_an_assessment_gives_the_failed_check_a_finding(repo, clock):
    content = small()
    assert len(content.edges) == 2  # the mapping and the requirement's place in its framework
    seeded(repo, clock, content)
    crawl_fixture(repo, clock, content=content)
    clock.advance(minutes=5)
    outcome = apply_assessment(repo, content.rules, content.dates, clock.now, clock)

    row = next(r for r in outcome.results if r.scope_id == SYSTEM)
    assert row.status is ImplementationStatus.NOT_IMPLEMENTED
    assert [f.subject for f in outcome.findings if f.code == "control_not_met"] == [SYSTEM]

    ca = f"ca:VC-060:{SYSTEM}"
    supports = repo.neighbors(ca, Direction.IN, EdgeType.SUPPORTS)
    assert [e.src for e in supports] == [row.evidence_id]
    assert len(of_type(repo, NodeType.CONTROL_ASSESSMENT)) >= 3


def test_assessing_at_the_start_of_the_day_misses_evidence_collected_later(clock):
    content = small()
    repo = InMemoryRepository("kestrel", clock)
    seeded(repo, clock, content)
    crawl_fixture(repo, clock, content=content)
    start_of_day = datetime(2026, 11, 6, tzinfo=UTC)
    earlier = apply_assessment(repo, content.rules, content.dates, start_of_day, clock)
    missed = next(r for r in earlier.results if r.scope_id == SYSTEM)
    assert missed.status is ImplementationStatus.NOT_ASSESSED
    clock.advance(minutes=1)
    later = apply_assessment(repo, content.rules, content.dates, clock.now, clock)
    seen = next(r for r in later.results if r.scope_id == SYSTEM)
    assert seen.status is ImplementationStatus.NOT_IMPLEMENTED


def test_assess_means_now_by_default_and_the_start_of_another_day(monkeypatch):
    fixed = datetime(2026, 11, 6, 15, 30, tzinfo=UTC)
    monkeypatch.setattr(cli, "_utc_now", lambda: fixed)
    seen = []
    real = cli.apply_assessment

    def spy(repo, rules, dates, as_of, clock, **kw):
        seen.append(as_of)
        return real(repo, rules, dates, as_of, clock, **kw)

    monkeypatch.setattr(cli, "apply_assessment", spy)
    root = str(CONTENT)
    for args in (
        ["assess"],
        ["assess", "--as-of", "2026-11-06"],
        ["assess", "--as-of", "2026-11-05"],
    ):
        assert cli.run([*args, "--content", root]) == cli.OK
    assert seen == [fixed, fixed, datetime(2026, 11, 5, tzinfo=UTC)]
