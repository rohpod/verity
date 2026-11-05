from datetime import date, timedelta

from assess_support import (
    AS_OF,
    COMMON,
    PROV,
    SYS,
    applies,
    attestation,
    automated_result,
    control,
    findings_of,
    maps,
    technical,
    verification,
    world,
)
from verity_core.model import ids
from verity_core.model.enums import (
    AppliesCondition,
    ScopeLevel,
    Source,
)
from verity_core.model.nodes import AISystem
from verity_core.rules.finding import Finding, Severity


def codes(findings, code=None):
    return [f.code for f in findings if code in (None, f.code)]


def setup(*, items=(), applications=None, controls=None, mappings=None, **kw):
    return world(
        controls=controls if controls is not None else [control("VC-001")],
        requirements=["a1"],
        mappings=mappings if mappings is not None else [maps("a1", "VC-001")],
        applications=applications if applications is not None else [applies("a1")],
        evidence_items=items,
        **kw,
    )


def test_a_clean_world_has_no_findings():
    assert findings_of(setup(items=[verification("VC-001")])) == []


def test_control_not_met_is_high_and_about_the_scope():
    found = findings_of(setup(items=[attestation("VC-001", "not_implemented")]))
    (f,) = [f for f in found if f.code == "control_not_met"]
    assert (f.severity, f.subject) == (Severity.HIGH, SYS)
    assert "VC-001" in f.message


def test_a_failed_automated_test_is_control_not_met():
    graph = setup(controls=[technical("VC-001")], items=[automated_result("VC-001", "fail")])
    assert codes(findings_of(graph), "control_not_met") == ["control_not_met"]


def test_no_evidence_is_high_when_a_requirement_behind_it_is_in_force():
    (f,) = [f for f in findings_of(setup()) if f.code == "no_evidence"]
    assert f.severity is Severity.HIGH


def test_no_evidence_is_high_when_the_requirement_is_conditional():
    applications = [applies("a1", condition=AppliesCondition.LEGACY_SIGNIFICANT_CHANGE)]
    (f,) = [f for f in findings_of(setup(applications=applications)) if f.code == "no_evidence"]
    assert f.severity is Severity.HIGH


def test_no_evidence_is_medium_when_every_requirement_behind_it_is_upcoming():
    applications = [applies("a1", in_force_from=date(2027, 12, 2))]
    (f,) = [f for f in findings_of(setup(applications=applications)) if f.code == "no_evidence"]
    assert f.severity is Severity.MEDIUM


def test_no_evidence_turns_high_on_the_day_the_requirement_comes_into_force():
    applications = [applies("a1", in_force_from=date(2026, 11, 6))]
    graph = setup(applications=applications)
    before = findings_of(graph, AS_OF)
    after = findings_of(graph, AS_OF + timedelta(days=1))
    assert [f.severity for f in before if f.code == "no_evidence"] == [Severity.MEDIUM]
    assert [f.severity for f in after if f.code == "no_evidence"] == [Severity.HIGH]


def test_one_in_force_requirement_is_enough_to_make_it_high():
    graph = world(
        controls=[control("VC-001")],
        requirements=["a1", "a2"],
        mappings=[maps("a1", "VC-001"), maps("a2", "VC-001")],
        applications=[applies("a1", in_force_from=date(2027, 12, 2)), applies("a2")],
    )
    assert [f.severity for f in findings_of(graph) if f.code == "no_evidence"] == [Severity.HIGH]


def test_provider_unknown_is_high_and_names_the_system():
    graph = setup(
        controls=[control("VC-050", scope=ScopeLevel.PROVIDER)],
        mappings=[maps("a1", "VC-050")],
        models=("unknown",),
    )
    (f,) = [f for f in findings_of(graph) if f.code == "provider_unknown"]
    assert (f.severity, f.subject) == (Severity.HIGH, SYS)


def test_provider_unknown_is_raised_not_hidden_as_not_applicable():
    graph = setup(
        controls=[control("VC-050", scope=ScopeLevel.PROVIDER)],
        mappings=[maps("a1", "VC-050")],
        models=("unknown",),
    )
    assert "provider_unknown" in codes(findings_of(graph))


def test_in_house_models_raise_no_provider_finding():
    graph = setup(
        controls=[control("VC-050", scope=ScopeLevel.PROVIDER)],
        mappings=[maps("a1", "VC-050")],
    )
    assert codes(findings_of(graph)) == []


def test_a_provider_gap_is_a_no_evidence_finding_on_the_provider():
    graph = setup(
        controls=[control("VC-050", scope=ScopeLevel.PROVIDER)],
        mappings=[maps("a1", "VC-050")],
        models=("known",),
    )
    (f,) = [f for f in findings_of(graph) if f.code == "no_evidence"]
    assert (f.subject, f.severity) == (PROV, Severity.HIGH)


def test_no_owner_is_medium():
    (f,) = [f for f in findings_of(setup(items=[verification("VC-001")], owner=False))]
    assert (f.code, f.severity, f.subject) == ("no_owner", Severity.MEDIUM, SYS)


def test_a_system_with_an_owner_has_no_no_owner_finding():
    assert "no_owner" not in codes(findings_of(setup()))


def test_evidence_expiring_is_low():
    soon = verification("VC-001", valid_until=AS_OF + timedelta(days=3))
    (f,) = findings_of(setup(items=[soon]))
    assert (f.code, f.severity) == ("evidence_expiring", Severity.LOW)


def test_evidence_with_longer_to_run_does_not_expire_yet():
    assert findings_of(setup(items=[verification("VC-001")])) == []


def test_conditional_obligation_is_one_low_finding_per_system():
    graph = world(
        controls=[control("VC-001")],
        requirements=["a1", "a2"],
        mappings=[maps("a1", "VC-001"), maps("a2", "VC-001")],
        applications=[
            applies("a1", condition=AppliesCondition.LEGACY_SIGNIFICANT_CHANGE),
            applies("a2", condition=AppliesCondition.LEGACY_SIGNIFICANT_CHANGE),
        ],
        evidence_items=[verification("VC-001")],
    )
    found = [f for f in findings_of(graph) if f.code == "conditional_obligation"]
    assert [(f.severity, f.subject) for f in found] == [(Severity.LOW, SYS)]


def test_an_unconditional_system_has_no_conditional_obligation():
    assert "conditional_obligation" not in codes(findings_of(setup()))


def test_findings_from_the_applicability_engine_are_passed_through():
    extra = [Finding("risk_tier_unconfirmed", Severity.HIGH, SYS, "Undecided.")]
    found = findings_of(setup(items=[verification("VC-001")]), extra=extra)
    assert codes(found) == ["risk_tier_unconfirmed"]


def test_findings_are_sorted_by_severity_then_code_and_are_stable():
    extra = [Finding("unknown_fact", Severity.MEDIUM, SYS, "x")]
    graph = setup(
        items=[verification("VC-001", valid_until=AS_OF + timedelta(days=1))], owner=False
    )
    found = findings_of(graph, extra=extra)
    assert [f.severity for f in found] == [Severity.MEDIUM, Severity.MEDIUM, Severity.LOW]
    assert codes(found) == ["no_owner", "unknown_fact", "evidence_expiring"]
    assert found == findings_of(graph, extra=extra)


def test_an_identical_finding_is_listed_once():
    extra = [Finding("unknown_fact", Severity.MEDIUM, SYS, "x")] * 2
    assert codes(findings_of(setup(items=[verification("VC-001")]), extra=extra)) == [
        "unknown_fact"
    ]


def test_a_system_without_any_obligation_still_gets_no_owner():
    other = AISystem(
        id=ids.system_id("t"), name="T", purpose="Invented", kind="classical_ml", **COMMON
    )
    graph = world(extra_nodes=[other])
    owners = [f for f in findings_of(graph) if f.code == "no_owner"]
    assert [f.subject for f in owners] == [other.id]


def test_a_simulated_sign_off_is_not_a_finding():
    ev = verification("VC-001", source=Source.SIMULATED)
    assert findings_of(setup(items=[ev])) == []
