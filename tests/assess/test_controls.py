from datetime import timedelta

import pytest
from assess_support import (
    AS_OF,
    EARLIER,
    LATER_VALID,
    PERSON,
    SYS,
    TENANT,
    applies,
    attestation,
    automated_result,
    control,
    evidence,
    maps,
    resource_and_change,
    status_of,
    technical,
    verification,
    world,
)
from verity_core.assess.controls import ControlAssessor
from verity_core.model.enums import (
    AssuranceLevel,
    EvidenceKind,
    ImplementationStatus,
    Source,
)
from verity_core.model.evidence import Evidence

S = ImplementationStatus
L = AssuranceLevel


def assess(controls, items, code="VC-001", as_of=AS_OF, extra=((), ())):
    graph = world(
        controls=controls, evidence_items=items, extra_nodes=extra[0], extra_edges=extra[1]
    )
    return ControlAssessor(graph, as_of).assess(f"ctl:{code}", SYS)


ORG_CTL = [control("VC-001")]
AUTO_CTL = [technical("VC-001")]


def test_no_evidence_is_not_assessed_at_l0():
    r = assess(ORG_CTL, [])
    assert (r.status, r.level, r.method) == (S.NOT_ASSESSED, L.L0_INFERRED, "no_evidence")
    assert r.assessor is None and r.evidence_id is None and r.source is Source.DERIVED


# row 1
def test_row_1_a_failed_test_on_an_automatable_control_is_not_implemented_at_l3():
    r = assess(AUTO_CTL, [automated_result("VC-001", "fail")])
    assert (r.status, r.level, r.method) == (S.NOT_IMPLEMENTED, L.L3_TESTED, "automated_test_fail")


def test_row_1_beats_a_verification_decision():
    r = assess(AUTO_CTL, [automated_result("VC-001", "fail"), verification("VC-001")])
    assert r.status is S.NOT_IMPLEMENTED and r.level is L.L3_TESTED


# row 2
def test_row_2_a_verification_is_as_decided_at_l4_with_its_assessor():
    for decided in ("implemented", "partially_implemented", "not_implemented"):
        r = assess(ORG_CTL, [verification("VC-001", decided)])
        assert r.status is S(decided)
        assert r.level is L.L4_VERIFIED
        assert r.assessor == PERSON
        assert r.method == "verification_decision"


def test_row_2_beats_a_passing_test_and_everything_lower():
    items = [automated_result("VC-001", "pass"), verification("VC-001", "partially_implemented")]
    r = assess(AUTO_CTL, items)
    assert r.status is S.PARTIALLY_IMPLEMENTED and r.level is L.L4_VERIFIED


def test_a_verification_decision_makes_a_non_automatable_control_implemented():
    r = assess(ORG_CTL, [verification("VC-001")])
    assert (r.status, r.level) == (S.IMPLEMENTED, L.L4_VERIFIED)


def test_a_verification_by_an_automated_collector_is_ignored():
    r = assess(ORG_CTL, [verification("VC-001", collector="crawler@0.1.0")])
    assert r.status is S.NOT_ASSESSED


# row 3
def test_row_3_a_passing_test_on_an_automatable_control_is_implemented_at_l3():
    r = assess(AUTO_CTL, [automated_result("VC-001", "pass")])
    assert (r.status, r.level, r.method) == (S.IMPLEMENTED, L.L3_TESTED, "automated_test_pass")
    assert r.assessor is None


def test_a_test_with_another_outcome_decides_nothing():
    assert assess(AUTO_CTL, [automated_result("VC-001", "error")]).status is S.NOT_ASSESSED


def test_the_latest_test_decides():
    items = [
        automated_result("VC-001", "fail", collected_at=EARLIER),
        automated_result("VC-001", "pass", collected_at=EARLIER + timedelta(days=1)),
    ]
    assert assess(AUTO_CTL, items).status is S.IMPLEMENTED
    items = [
        automated_result("VC-001", "pass", collected_at=EARLIER),
        automated_result("VC-001", "fail", collected_at=EARLIER + timedelta(days=1)),
    ]
    assert assess(AUTO_CTL, items).status is S.NOT_IMPLEMENTED


# row 4
@pytest.mark.parametrize("controls", [ORG_CTL, AUTO_CTL])
def test_row_4_a_document_is_partially_implemented_at_l2(controls):
    r = assess(controls, [evidence("VC-001", EvidenceKind.DOCUMENT_REF, path="evidence/x.md")])
    assert (r.status, r.level, r.method) == (
        S.PARTIALLY_IMPLEMENTED,
        L.L2_EVIDENCED,
        "document_ref",
    )


# row 5
def test_row_5_an_automated_snapshot_on_an_automatable_control_is_partial_at_l2():
    snap = evidence("VC-001", EvidenceKind.CONFIG_SNAPSHOT, collector="crawler@0.1.0")
    r = assess(AUTO_CTL, [snap])
    assert (r.status, r.level) == (S.PARTIALLY_IMPLEMENTED, L.L2_EVIDENCED)
    assert r.method == "automated_config_snapshot"


def test_a_snapshot_counts_for_nothing_on_a_non_automatable_control():
    snap = evidence("VC-001", EvidenceKind.CONFIG_SNAPSHOT, collector="crawler@0.1.0")
    assert assess(ORG_CTL, [snap]).status is S.NOT_ASSESSED


def test_a_snapshot_by_a_person_is_not_automated():
    snap = evidence("VC-001", EvidenceKind.CONFIG_SNAPSHOT, collector=PERSON)
    assert assess(AUTO_CTL, [snap]).status is S.NOT_ASSESSED


# rows 6 and 7
def test_row_6_an_attestation_of_not_implemented_is_not_implemented_at_l1():
    r = assess(ORG_CTL, [attestation("VC-001", "not_implemented")])
    assert (r.status, r.level, r.method) == (
        S.NOT_IMPLEMENTED,
        L.L1_DECLARED,
        "attestation_not_implemented",
    )


@pytest.mark.parametrize("said", ["implemented", "partially_implemented"])
def test_row_7_any_other_attestation_is_partially_implemented_at_l1(said):
    r = assess(ORG_CTL, [attestation("VC-001", said)])
    assert (r.status, r.level, r.method) == (S.PARTIALLY_IMPLEMENTED, L.L1_DECLARED, "attestation")


def test_a_document_beats_an_attestation():
    items = [
        attestation("VC-001"),
        evidence("VC-001", EvidenceKind.DOCUMENT_REF, path="evidence/x.md"),
    ]
    assert assess(ORG_CTL, items).level is L.L2_EVIDENCED


# row 8, and what counts for nothing
@pytest.mark.parametrize(
    "kind", [EvidenceKind.USAGE_RECORD, EvidenceKind.ATTESTATION, EvidenceKind.CONFIG_SNAPSHOT]
)
def test_row_8_evidence_that_matches_no_row_is_not_assessed(kind):
    # An attestation with no decision_kind is not a decision.
    r = assess(ORG_CTL, [evidence("VC-001", kind)])
    assert (r.status, r.level) == (S.NOT_ASSESSED, L.L0_INFERRED)


def test_automated_evidence_for_a_non_automatable_control_counts_for_nothing():
    items = [automated_result("VC-001", "pass"), automated_result("VC-001", "fail")]
    assert assess(ORG_CTL, items).status is S.NOT_ASSESSED


def test_evidence_for_another_control_or_scope_does_not_count():
    other_control = verification("VC-002")
    other_scope = verification("VC-001", scope="org:kestrel")
    assert assess(ORG_CTL, [other_control, other_scope]).status is S.NOT_ASSESSED


def test_evidence_collected_after_as_of_is_not_usable_yet():
    future = verification("VC-001", collected_at=AS_OF + timedelta(seconds=1))
    assert assess(ORG_CTL, [future]).status is S.NOT_ASSESSED
    on_time = verification("VC-001", collected_at=AS_OF)
    assert assess(ORG_CTL, [on_time]).status is S.IMPLEMENTED


# source
def test_source_is_simulated_when_the_deciding_evidence_is():
    r = assess(ORG_CTL, [verification("VC-001", source=Source.SIMULATED)])
    assert r.source is Source.SIMULATED
    assert assess(ORG_CTL, [verification("VC-001")]).source is Source.DERIVED


def test_source_follows_the_deciding_evidence_not_a_lower_one():
    items = [
        verification("VC-001"),
        attestation("VC-001", source=Source.SIMULATED),
    ]
    assert assess(ORG_CTL, items).source is Source.DERIVED


# D3: stale evidence drops the level
def test_d3_evidence_past_valid_until_drops_the_assessment_to_not_assessed():
    ev = evidence("VC-001", EvidenceKind.DOCUMENT_REF, valid_until=AS_OF + timedelta(days=30))
    assert assess(ORG_CTL, [ev]).level is L.L2_EVIDENCED
    later = AS_OF + timedelta(days=30, seconds=1)
    r = assess(ORG_CTL, [ev], as_of=later)
    assert (r.status, r.level) == (S.NOT_ASSESSED, L.L0_INFERRED)


def test_d3_evidence_is_still_usable_at_exactly_valid_until():
    ev = evidence("VC-001", EvidenceKind.DOCUMENT_REF, valid_until=AS_OF)
    assert assess(ORG_CTL, [ev]).level is L.L2_EVIDENCED


def test_d3_stale_evidence_falls_through_to_a_lower_row():
    old = verification("VC-001", valid_until=AS_OF - timedelta(days=1))
    fresh = attestation("VC-001")
    r = assess(ORG_CTL, [old, fresh])
    assert (r.status, r.level) == (S.PARTIALLY_IMPLEMENTED, L.L1_DECLARED)


def test_d3_a_change_detected_after_collection_makes_the_evidence_stale():
    ev = evidence(
        "VC-001", EvidenceKind.CONFIG_SNAPSHOT, collector="crawler@0.1.0", collected_at=EARLIER
    )
    nodes, edges = resource_and_change(EARLIER + timedelta(days=1), ev)
    assert assess(AUTO_CTL, [ev], extra=(nodes, edges)).status is S.NOT_ASSESSED


def test_d3_evidence_collected_after_the_change_recovers_it():
    ev = evidence(
        "VC-001",
        EvidenceKind.CONFIG_SNAPSHOT,
        collector="crawler@0.1.0",
        collected_at=EARLIER + timedelta(days=2),
    )
    nodes, edges = resource_and_change(EARLIER + timedelta(days=1), ev)
    assert assess(AUTO_CTL, [ev], extra=(nodes, edges)).level is L.L2_EVIDENCED


def test_d3_a_change_not_yet_detected_at_as_of_does_not_count():
    ev = evidence(
        "VC-001", EvidenceKind.CONFIG_SNAPSHOT, collector="crawler@0.1.0", collected_at=EARLIER
    )
    nodes, edges = resource_and_change(AS_OF + timedelta(days=1), ev)
    assert assess(AUTO_CTL, [ev], extra=(nodes, edges)).level is L.L2_EVIDENCED


def test_a_change_never_touches_evidence_not_collected_from_the_resource():
    ev = verification("VC-001", collected_at=EARLIER)
    other = evidence(
        "VC-002", EvidenceKind.CONFIG_SNAPSHOT, collector="crawler@0.1.0", collected_at=EARLIER
    )
    nodes, edges = resource_and_change(EARLIER + timedelta(days=1), other)
    assert assess(ORG_CTL, [ev, other], extra=(nodes, edges)).level is L.L4_VERIFIED


def test_the_assessor_remembers_what_it_assessed_in_order():
    graph = world(controls=[control("VC-002"), control("VC-001")])
    a = ControlAssessor(graph, AS_OF)
    a.assess("ctl:VC-002", SYS)
    a.assess("ctl:VC-001", SYS)
    a.assess("ctl:VC-001", SYS)
    assert [r.control_id for r in a.results()] == ["ctl:VC-001", "ctl:VC-002"]


def test_the_assessor_refuses_a_naive_as_of_and_a_missing_control():
    graph = world()
    with pytest.raises(ValueError, match="timezone-aware"):
        ControlAssessor(graph, AS_OF.replace(tzinfo=None))
    with pytest.raises(ValueError, match="not a control"):
        ControlAssessor(graph, AS_OF).assess("ctl:VC-404", SYS)


def test_valid_until_in_the_far_future_is_fresh():
    ev = verification("VC-001", valid_until=LATER_VALID)
    assert assess(ORG_CTL, [ev]).freshness.value == "fresh"


# --- decisions replaced or withdrawn (ADR 0020) ----------------------------------------------


def revocation_of(*decision_ids, collected_at=EARLIER + timedelta(days=1), scope=SYS):
    return Evidence.build(
        subject=scope,
        collector=PERSON,
        collected_at=collected_at,
        valid_until=LATER_VALID,
        kind=EvidenceKind.ATTESTATION,
        content={
            "decision_id": "r1",
            "decision_kind": "revocation",
            "subject": scope,
            "supersedes": list(decision_ids),
        },
        tenant=TENANT,
        source=Source.SYNTHETIC,
    )


def test_a_superseding_decision_wins_whatever_the_ids_hash_to():
    for n in range(50):  # same day, so the Evidence ID used to decide
        old = verification("VC-001", decision_id="v1", valid_until=LATER_VALID + timedelta(hours=n))
        new = verification(
            "VC-001",
            "not_implemented",
            decision_id="v2",
            supersedes=["v1"],
            valid_until=LATER_VALID + timedelta(minutes=n),
        )
        r = assess(ORG_CTL, [old, new])
        assert (r.status, r.level) == (S.NOT_IMPLEMENTED, L.L4_VERIFIED), n


def test_the_superseding_decision_may_improve_a_verdict_too():
    for n in range(20):
        old = verification("VC-001", "not_implemented", decision_id="v1")
        new = verification(
            "VC-001",
            decision_id="v2",
            supersedes=["v1"],
            valid_until=LATER_VALID + timedelta(minutes=n),
        )
        assert assess(ORG_CTL, [old, new]).status is S.IMPLEMENTED, n


def test_a_revocation_takes_an_l4_sign_off_away():
    ev = verification("VC-001", decision_id="v1")
    assert assess(ORG_CTL, [ev]).level is L.L4_VERIFIED
    r = assess(ORG_CTL, [ev, revocation_of("v1")])
    assert (r.status, r.level, r.method) == (S.NOT_ASSESSED, L.L0_INFERRED, "no_evidence")


def test_a_revocation_does_not_count_before_it_was_made():
    ev = verification("VC-001", decision_id="v1")
    gone = revocation_of("v1", collected_at=AS_OF - timedelta(days=1))
    assert assess(ORG_CTL, [ev, gone], as_of=AS_OF - timedelta(days=2)).level is L.L4_VERIFIED
    assert assess(ORG_CTL, [ev, gone], as_of=AS_OF).level is L.L0_INFERRED


def test_a_revocation_is_not_itself_an_assessment():
    r = assess(ORG_CTL, [revocation_of("v0")])
    assert r.method == "no_evidence"


def test_a_requirement_falls_back_when_its_only_sign_off_is_revoked():
    ev = verification("VC-001", decision_id="v1")
    kwargs = {"controls": ORG_CTL, "requirements": ["a"], "mappings": [maps("a", "VC-001")]}
    kwargs["applications"] = [applies("a")]
    graph = world(evidence_items=[ev], **kwargs)
    assert status_of(graph, "a").state.value == "satisfied"
    graph = world(evidence_items=[ev, revocation_of("v1")], **kwargs)
    assert status_of(graph, "a").state.value == "not_met"
