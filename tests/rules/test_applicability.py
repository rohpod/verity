from datetime import UTC, date, datetime, timedelta

import pytest
from rules_support import (
    CONTENT,
    DEPLOYER_REQS,
    ORG,
    PROVIDER_REQS,
    codes,
    date_of,
    decision,
    edges_to,
    run,
    system,
)
from verity_core.model.edges import AppliesToEdge
from verity_core.model.enums import AppliesCondition, Role, Source
from verity_core.rules.finding import Severity
from verity_core.rules.status import ApplicabilityStatus, applicability_status

P, D = Role.PROVIDER, Role.DEPLOYER
ANNEX_III = date_of("euaia-high-risk-annex-iii")  # 2027-12-02
GENERAL = date_of("euaia-general")  # 2026-08-02
LEGACY_50_2 = date_of("euaia-art50-2-legacy")
BEFORE = ANNEX_III - timedelta(days=1)
LONG_AGO = date(2026, 6, 15)


def hr(slug="hr", **facts):
    """A high-risk employment system, confirmed unless the test says otherwise."""
    facts = {
        "roles": [P, D],
        "use_domains": ["employment"],
        "interacts_with_people": False,
        "generates_synthetic_content": False,
    } | facts
    return system(slug, **facts)


def confirmed(s, on=date(2026, 11, 5)):
    return decision(s.id, "high_risk", on)


# --- eu-literacy: Art. 4, one edge per role held by any system -----------------------------


def test_literacy_has_an_edge_per_role_that_any_system_holds():
    edges, _ = run(system("a", roles=[P]), system("b", roles=[D]))
    found = edges_to(edges, ORG)
    assert {k for k in found if k[0] == "art4"} == {("art4", P), ("art4", D)}


def test_literacy_has_only_the_roles_that_are_held():
    edges, _ = run(system("a", roles=[D]))
    assert {k for k in edges_to(edges, ORG) if k[0] == "art4"} == {("art4", D)}


@pytest.mark.parametrize("roles", [[], [Role.IMPORTER], [Role.DISTRIBUTOR]])
def test_literacy_ignores_roles_other_than_provider_and_deployer(roles):
    edges, _ = run(system("a", roles=roles))
    assert not [e for e in edges if e.rule_id == "eu-literacy"]


def test_literacy_has_no_edge_without_systems():
    edges, _ = run()
    assert not [e for e in edges if e.rule_id == "eu-literacy"]


def test_literacy_takes_its_date_from_chapters_1_and_2():
    edges, _ = run(system("a", roles=[P], interacts_with_people=False))
    (edge,) = (e for e in edges if e.rule_id == "eu-literacy")
    assert edge.in_force_from == date_of("euaia-chapters-1-2")
    assert edge.condition is None


def test_nothing_applies_without_an_organisation_to_the_organisation():
    edges, _ = run(system("a", roles=[P]), organisation=False)
    assert not [e for e in edges if e.dst == ORG]


# --- eu-disclosure: Art. 50(1) -------------------------------------------------------------


def test_disclosure_applies_to_a_provider_that_interacts_with_people():
    s = system("chat", roles=[P], interacts_with_people=True)
    edges, _ = run(s)
    edge = edges_to(edges, s.id)[("art50-1", P)]
    assert edge.in_force_from == GENERAL
    assert edge.rule_id == "eu-disclosure"


def test_disclosure_is_not_for_a_deployer_only():
    s = system("chat", roles=[D], interacts_with_people=True)
    edges, _ = run(s)
    assert ("art50-1", P) not in edges_to(edges, s.id)
    assert ("art50-1", D) not in edges_to(edges, s.id)


def test_disclosure_does_not_apply_when_nobody_interacts_and_raises_nothing():
    s = system("batch", roles=[P], interacts_with_people=False, generates_synthetic_content=False)
    edges, findings = run(s)
    assert ("art50-1", P) not in edges_to(edges, s.id)
    assert codes(findings, s.id) == []


def test_disclosure_with_an_unknown_fact_does_not_fire_and_raises_unknown_fact():
    s = system("chat", roles=[P])
    edges, findings = run(s)
    assert ("art50-1", P) not in edges_to(edges, s.id)
    (finding,) = [f for f in findings if f.subject == s.id and "interacts" in f.message]
    assert finding.code == "unknown_fact"
    assert finding.severity is Severity.MEDIUM


# --- eu-marking: Art. 50(2), with its legacy date ------------------------------------------


def marking(placed):
    s = system(
        "gen",
        roles=[P],
        interacts_with_people=False,
        generates_synthetic_content=True,
        first_placed_on_market=placed,
    )
    edges, findings = run(s)
    return edges_to(edges, s.id).get(("art50-2", P)), findings


def test_marking_uses_the_legacy_date_for_a_system_placed_the_day_before_the_general_date():
    edge, findings = marking(GENERAL - timedelta(days=1))
    assert edge.in_force_from == LEGACY_50_2
    assert findings == []


def test_marking_uses_the_general_date_for_a_system_placed_on_the_general_date():
    edge, _ = marking(GENERAL)
    assert edge.in_force_from == GENERAL


def test_marking_uses_the_general_date_for_a_later_system():
    edge, _ = marking(GENERAL + timedelta(days=1))
    assert edge.in_force_from == GENERAL


def test_marking_with_an_unknown_placing_date_takes_the_general_date_and_raises_unknown_fact():
    edge, findings = marking(None)
    assert edge.in_force_from == GENERAL
    assert [(f.code, "first_placed_on_market" in f.message) for f in findings] == [
        ("unknown_fact", True)
    ]


def test_marking_with_unknown_synthetic_content_does_not_fire():
    s = system("gen", roles=[P], first_placed_on_market=date(2026, 3, 2))
    edges, findings = run(s)
    assert ("art50-2", P) not in edges_to(edges, s.id)
    assert any("generates_synthetic_content" in f.message for f in findings)


def test_marking_does_not_apply_when_nothing_is_generated():
    s = system("gen", roles=[P], interacts_with_people=False, generates_synthetic_content=False)
    edges, findings = run(s)
    assert ("art50-2", P) not in edges_to(edges, s.id)
    assert findings == []


def test_the_legacy_date_boundary_reads_as_upcoming_then_in_force():
    edge, _ = marking(date(2026, 3, 2))
    before = datetime(2026, 12, 1, tzinfo=UTC)
    on = datetime(2026, 12, 2, tzinfo=UTC)
    assert applicability_status(edge, before) is ApplicabilityStatus.UPCOMING
    assert applicability_status(edge, on) is ApplicabilityStatus.IN_FORCE


# --- the risk tier --------------------------------------------------------------------------


def chapter_iii(edges, s):
    found = edges_to(edges, s.id)
    return {k for k in found if k[0] in PROVIDER_REQS + DEPLOYER_REQS}


def test_a_confirmed_system_has_chapter_iii_rules_and_no_finding():
    s = hr(first_placed_on_market=LONG_AGO)
    edges, findings = run(s, decisions=(confirmed(s),))
    assert chapter_iii(edges, s) == {(r, P) for r in PROVIDER_REQS} | {
        (r, D) for r in DEPLOYER_REQS
    }
    assert codes(findings, s.id) == []


def test_a_rejected_system_has_no_chapter_iii_rules_and_no_finding():
    s = hr()
    edges, findings = run(s, decisions=(decision(s.id, "not_high_risk", date(2026, 11, 5)),))
    assert chapter_iii(edges, s) == set()
    assert codes(findings, s.id) == []


def test_an_undecided_annex_iii_system_is_a_candidate_with_rules_and_a_finding():
    s = hr()
    edges, findings = run(s)
    assert len(chapter_iii(edges, s)) == len(PROVIDER_REQS) + len(DEPLOYER_REQS)
    (finding,) = [f for f in findings if f.code == "risk_tier_unconfirmed"]
    assert (finding.subject, finding.severity) == (s.id, Severity.HIGH)


def test_a_system_outside_annex_iii_is_not_high_risk_and_raises_nothing():
    s = hr(use_domains=["customer_support"])
    edges, findings = run(s)
    assert chapter_iii(edges, s) == set()
    assert codes(findings, s.id) == []


def test_a_decision_makes_a_system_high_risk_whatever_its_domain():
    s = hr(use_domains=["customer_support"], first_placed_on_market=LONG_AGO)
    edges, findings = run(s, decisions=(confirmed(s),))
    assert len(chapter_iii(edges, s)) == len(PROVIDER_REQS) + len(DEPLOYER_REQS)
    assert codes(findings, s.id) == []


def test_the_latest_decision_wins():
    s = hr()
    reject = decision(s.id, "not_high_risk", date(2026, 11, 6), "later")
    edges, _ = run(s, decisions=(confirmed(s, date(2026, 11, 5)), reject))
    assert chapter_iii(edges, s) == set()
    edges, _ = run(
        s,
        decisions=(
            decision(s.id, "not_high_risk", date(2026, 11, 5)),
            confirmed(s, date(2026, 11, 6)),
        ),
    )
    assert chapter_iii(edges, s)


def test_another_systems_decision_does_not_count():
    a, b = hr("a"), hr("b")
    _, findings = run(a, b, decisions=(confirmed(a),))
    assert [f.subject for f in findings if f.code == "risk_tier_unconfirmed"] == [b.id]


def test_a_non_tier_decision_does_not_confirm_a_candidate():
    s = hr()
    other = decision(s.id, "high_risk", date(2026, 11, 5))
    other = other.model_copy(update={"content": {"decision_kind": "verification"}})
    _, findings = run(s, decisions=(other,))
    assert "risk_tier_unconfirmed" in codes(findings)


# --- roles in the high-risk rules ------------------------------------------------------------


def test_the_provider_rules_need_the_provider_role():
    s = hr(roles=[D])
    edges, _ = run(s, decisions=(confirmed(s),))
    assert chapter_iii(edges, s) == {(r, D) for r in DEPLOYER_REQS}


def test_the_deployer_rules_need_the_deployer_role():
    s = hr(roles=[P])
    edges, _ = run(s, decisions=(confirmed(s),))
    assert chapter_iii(edges, s) == {(r, P) for r in PROVIDER_REQS}


def test_a_high_risk_importer_gets_no_chapter_iii_rules():
    s = hr(roles=[Role.IMPORTER])
    edges, _ = run(s, decisions=(confirmed(s),))
    assert chapter_iii(edges, s) == set()


# --- Art. 111(2) -----------------------------------------------------------------------------


def chapter_edge(**facts):
    s = hr(**facts)
    edges, findings = run(s, decisions=(confirmed(s),))
    return edges_to(edges, s.id)[("art9", P)], findings


def test_a_system_placed_before_annex_iii_is_conditional_with_no_change():
    edge, findings = chapter_edge(first_placed_on_market=LONG_AGO)
    assert edge.condition is AppliesCondition.LEGACY_SIGNIFICANT_CHANGE
    assert edge.in_force_from == ANNEX_III
    assert findings == []


def test_the_day_before_annex_iii_is_still_legacy():
    edge, _ = chapter_edge(first_placed_on_market=BEFORE)
    assert edge.condition is AppliesCondition.LEGACY_SIGNIFICANT_CHANGE


def test_a_system_placed_on_the_annex_iii_date_is_not_legacy():
    edge, _ = chapter_edge(first_placed_on_market=ANNEX_III)
    assert edge.condition is None
    assert edge.in_force_from == ANNEX_III


def test_a_system_placed_after_annex_iii_is_not_legacy():
    edge, _ = chapter_edge(first_placed_on_market=ANNEX_III + timedelta(days=30))
    assert edge.condition is None
    assert edge.in_force_from == ANNEX_III


def test_a_change_before_annex_iii_leaves_it_conditional():
    edge, _ = chapter_edge(first_placed_on_market=LONG_AGO, significant_change_on=BEFORE)
    assert edge.condition is AppliesCondition.LEGACY_SIGNIFICANT_CHANGE
    assert edge.in_force_from == ANNEX_III


def test_a_change_on_the_annex_iii_date_brings_it_into_scope_from_that_date():
    edge, _ = chapter_edge(first_placed_on_market=LONG_AGO, significant_change_on=ANNEX_III)
    assert edge.condition is None
    assert edge.in_force_from == ANNEX_III


def test_a_change_after_annex_iii_brings_it_into_scope_from_the_change():
    change = ANNEX_III + timedelta(days=90)
    edge, _ = chapter_edge(first_placed_on_market=LONG_AGO, significant_change_on=change)
    assert edge.condition is None
    assert edge.in_force_from == change


def test_a_change_means_nothing_to_a_system_that_is_not_legacy():
    change = ANNEX_III + timedelta(days=90)
    edge, _ = chapter_edge(first_placed_on_market=ANNEX_III, significant_change_on=change)
    assert edge.in_force_from == ANNEX_III


def test_an_unknown_placing_date_takes_the_non_legacy_path_and_raises_unknown_fact():
    edge, findings = chapter_edge()
    assert edge.condition is None
    assert edge.in_force_from == ANNEX_III
    assert [(f.code, "first_placed_on_market" in f.message) for f in findings] == [
        ("unknown_fact", True)
    ]


def test_the_unknown_placing_date_is_raised_once_however_many_rules_read_it():
    _, findings = chapter_edge()
    assert len(findings) == 1


def test_the_deployer_rules_apply_it_too():
    s = hr(first_placed_on_market=LONG_AGO)
    edges, _ = run(s, decisions=(confirmed(s),))
    assert (
        edges_to(edges, s.id)[("art26", D)].condition is AppliesCondition.LEGACY_SIGNIFICANT_CHANGE
    )


def test_it_is_not_extended_to_art_50_or_art_4():
    s = hr(
        first_placed_on_market=LONG_AGO,
        interacts_with_people=True,
        generates_synthetic_content=True,
    )
    edges, _ = run(s, decisions=(confirmed(s),))
    found = edges_to(edges, s.id)
    assert found[("art50-1", P)].condition is None
    assert found[("art50-2", P)].condition is None
    assert all(e.condition is None for e in edges if e.dst == ORG)


def test_a_conditional_edge_reads_as_conditional_before_and_after_annex_iii():
    edge, _ = chapter_edge(first_placed_on_market=LONG_AGO)
    for when in (ANNEX_III - timedelta(days=1), ANNEX_III, ANNEX_III + timedelta(days=500)):
        status = applicability_status(edge, datetime(when.year, when.month, when.day, tzinfo=UTC))
        assert status is ApplicabilityStatus.CONDITIONAL


def test_a_non_legacy_edge_reads_as_upcoming_then_in_force_at_annex_iii():
    edge, _ = chapter_edge(first_placed_on_market=ANNEX_III)
    day = datetime(ANNEX_III.year, ANNEX_III.month, ANNEX_III.day, tzinfo=UTC)
    assert applicability_status(edge, day - timedelta(seconds=1)) is ApplicabilityStatus.UPCOMING
    assert applicability_status(edge, day) is ApplicabilityStatus.IN_FORCE


# --- adopted frameworks ----------------------------------------------------------------------


def test_every_leaf_of_the_adopted_frameworks_applies_to_the_organisation_in_any_role():
    edges, _ = run()
    adopted = [e for e in edges if e.rule_id == "adopted-frameworks"]
    parents = {
        e.dst for e in CONTENT.edges if e.src.startswith("req:") and e.dst.startswith("req:")
    }
    leaves = {
        r.id
        for r in CONTENT.requirements
        if r.id.split(":")[1] in {"nistrmf", "iso42001", "iso27001"} and r.id not in parents
    }
    assert {e.src for e in adopted} == leaves
    assert len(adopted) == len(leaves) > 0
    assert {e.role for e in adopted} == {Role.ANY}
    assert {e.in_force_from for e in adopted} == {None}
    assert {e.dst for e in adopted} == {ORG}
    assert all(e.condition is None for e in adopted)


def test_the_eu_act_is_not_in_the_adopted_frameworks():
    edges, _ = run()
    assert not [e for e in edges if e.rule_id == "adopted-frameworks" and ":euaia:" in e.src]


# --- the edges themselves --------------------------------------------------------------------


def test_edges_are_derived_and_the_reason_names_the_rule():
    s = hr(first_placed_on_market=LONG_AGO)
    edges, _ = run(s, decisions=(confirmed(s),))
    assert edges
    for e in edges:
        assert isinstance(e, AppliesToEdge)
        assert e.source is Source.DERIVED
        assert f"Rule {e.rule_id}" in e.reason
        assert e.reason.endswith(".")
    reason = edges_to(edges, s.id)[("art9", P)].reason
    assert "hr" in reason and "Art. 111(2)" in reason and "high-risk" in reason


def test_a_candidate_reason_says_it_is_undecided():
    s = hr()
    edges, _ = run(s)
    assert "not yet decided" in edges_to(edges, s.id)[("art9", P)].reason


def test_one_edge_per_requirement_target_and_role():
    s = hr()
    edges, _ = run(s, decisions=(confirmed(s),))
    keys = [(e.src, e.dst, e.role) for e in edges]
    assert len(keys) == len(set(keys))


def test_the_result_is_deterministic_and_sorted():
    systems = (hr("b"), hr("a"), system("c", roles=[P], interacts_with_people=True))
    first = run(*systems)
    assert first == run(*reversed(systems))
    edges, findings = first
    assert [(e.src, e.dst, e.role.value) for e in edges] == sorted(
        (e.src, e.dst, e.role.value) for e in edges
    )
    assert [(f.code, f.subject, f.message) for f in findings] == sorted(
        (f.code, f.subject, f.message) for f in findings
    )


def test_every_rule_in_the_real_file_fires_for_a_suitable_system():
    s = hr(interacts_with_people=True, generates_synthetic_content=True)
    edges, _ = run(s, decisions=(confirmed(s),))
    assert {e.rule_id for e in edges} == {r.id for r in CONTENT.rules.rules}
