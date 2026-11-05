"""M5's validation criteria, run against the real files under `content/` (ADR 0019)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from verity_core.assess.apply import apply_assessment
from verity_core.assess.requirements import RequirementState
from verity_core.content.loader import load_content
from verity_core.content.seed import seed
from verity_core.graph.memory import InMemoryRepository
from verity_core.model import ids
from verity_core.model.edges import AppliesToEdge
from verity_core.model.enums import (
    AssuranceLevel,
    Direction,
    EdgeType,
    ImplementationStatus,
    Role,
    Source,
)
from verity_core.rules.status import ApplicabilityStatus, applicability_status

REAL = Path(__file__).parents[2] / "content"
AS_OF = datetime(2026, 11, 5, tzinfo=UTC)
LATER = datetime(2026, 12, 2, tzinfo=UTC)
ISO = ("iso42001", "iso27001")


@pytest.fixture(scope="module")
def content():
    return load_content(REAL)


def assessed(content, as_of=AS_OF):
    clock = [datetime(2026, 11, 5, 9, tzinfo=UTC)]
    repo = InMemoryRepository("kestrel", lambda: clock[0])
    seed(repo, content, lambda: clock[0])
    clock[0] += timedelta(minutes=5)
    result = apply_assessment(repo, content.rules, content.dates, as_of, lambda: clock[0])
    return repo, result, clock


@pytest.fixture(scope="module")
def run(content):
    return assessed(content)


def ca(run, control, scope):
    repo, *_ = run
    node = repo.get_node(ids.ca_id(ids.control_id(control), scope))
    assert node is not None, (control, scope)
    return node


def findings(run, code, subject=None):
    return [f for f in run[1].findings if f.code == code and subject in (None, f.subject)]


def edge(run, requirement, system, role=Role.PROVIDER):
    repo, *_ = run
    found = [
        e
        for e in repo.neighbors(system, Direction.IN, EdgeType.APPLIES_TO)
        if e.src == ids.requirement_id("euaia", requirement) and e.role is role
    ]
    assert len(found) == 1, (requirement, system, role)
    assert isinstance(found[0], AppliesToEdge)
    return found[0]


def test_the_bias_test_gap_is_a_finding(run):
    assert any("VC-014" in f.message for f in findings(run, "no_evidence", "sys:talent-screening"))


def test_the_dpa_gap_is_a_finding(run):
    assert any("VC-050" in f.message for f in findings(run, "no_evidence", "prov:mock-openai"))


def test_the_mock_bedrock_dpa_is_partially_implemented_at_l2(run):
    node = ca(run, "VC-050", "prov:mock-bedrock")
    assert node.status is ImplementationStatus.PARTIALLY_IMPLEMENTED
    assert node.assurance_level is AssuranceLevel.L2_EVIDENCED


def test_the_simulated_verification_is_implemented_at_l4(run):
    node = ca(run, "VC-032", "sys:talent-screening")
    assert node.status is ImplementationStatus.IMPLEMENTED
    assert node.assurance_level is AssuranceLevel.L4_VERIFIED
    assert node.source is Source.SIMULATED
    assert node.assessor == "person:l-ivanova"


def test_talent_screening_chapter_iii_is_conditional(run):
    status = applicability_status(edge(run, "art9-2a", "sys:talent-screening"), AS_OF)
    assert status is ApplicabilityStatus.CONDITIONAL


def test_talent_screening_stays_conditional_when_dates_move(run):
    later = datetime(2027, 12, 2, tzinfo=UTC)
    status = applicability_status(edge(run, "art9-2a", "sys:talent-screening"), later)
    assert status is ApplicabilityStatus.CONDITIONAL


def test_art_50_2_on_the_support_assistant_comes_into_force_on_2_december(run):
    e = edge(run, "art50-2", "sys:support-assistant")
    assert applicability_status(e, AS_OF) is ApplicabilityStatus.UPCOMING
    assert applicability_status(e, LATER) is ApplicabilityStatus.IN_FORCE


def test_art_50_1_on_the_support_assistant_is_in_force(run):
    e = edge(run, "art50-1", "sys:support-assistant")
    assert applicability_status(e, AS_OF) is ApplicabilityStatus.IN_FORCE


def test_the_cv_parser_risk_tier_is_unconfirmed(run):
    assert findings(run, "risk_tier_unconfirmed", "sys:candidate-cv-parser")


def test_onboarding_coach_has_no_chapter_iii_edges(run):
    repo, *_ = run
    edges = repo.neighbors("sys:onboarding-coach", Direction.IN, EdgeType.APPLIES_TO)
    chapter_iii = {"art9", "art10", "art11", "art12", "art13", "art14", "art25-4", "art26"}
    assert not [e for e in edges if e.src.split(":")[-1].split("-")[0] in chapter_iii]
    assert not findings(run, "risk_tier_unconfirmed", "sys:onboarding-coach")


def test_the_legacy_faq_bot_has_no_owner(run):
    assert findings(run, "no_owner", "sys:legacy-faq-bot")


def test_meeting_minutes_draft_has_provider_unknown_and_is_never_not_applicable(run):
    assert findings(run, "provider_unknown", "sys:meeting-minutes-draft")
    states = [
        s
        for s in run[1].statuses
        if s.system_id == "sys:meeting-minutes-draft"
        and any(t.control_id.endswith(("VC-050", "VC-051")) for t in s.targets)
    ]
    assert states
    assert all(s.state is not RequirementState.NOT_APPLICABLE for s in states)


def test_no_iso_requirement_is_ever_satisfied(run):
    iso = [s for s in run[1].statuses if s.requirement_id.split(":")[1] in ISO]
    assert iso
    assert not [s for s in iso if s.state is RequirementState.SATISFIED]


def test_assessing_twice_writes_nothing_the_second_time(content):
    repo, first, clock = assessed(content)
    assert first.total_written > 0
    clock[0] += timedelta(minutes=5)
    second = apply_assessment(repo, content.rules, content.dates, AS_OF, lambda: clock[0])
    assert second.total_written == 0
    assert second.unchanged_assessments == len(second.results)


def test_every_satisfied_requirement_in_the_demo_rests_on_a_simulated_sign_off(run):
    satisfied = [s for s in run[1].statuses if s.state is RequirementState.SATISFIED]
    assert satisfied
    assert all(s.simulated for s in satisfied)
