"""No automated input may make a non-automatable control Implemented (M5 criterion, ADR 0019).

An exhaustive check without a property-testing dependency: every control kind and automatable
flag, against every evidence kind, outcome, collector, freshness and decision shape, alone and in
pairs. The only evidence allowed to produce Implemented for a non-automatable control is a
verification decision by a person.
"""

import itertools
from datetime import timedelta

import pytest
from assess_support import AS_OF, EARLIER, PERSON, SYS, evidence
from verity_core.assess.controls import decide
from verity_core.model import ids
from verity_core.model.enums import (
    AssuranceLevel,
    ControlKind,
    EvidenceKind,
    ImplementationStatus,
    ScopeLevel,
    Source,
)
from verity_core.model.nodes import Control

CONTROLS = [
    (kind, automatable)
    for kind, automatable in itertools.product(ControlKind, (False, True))
    if kind is ControlKind.TECHNICAL or not automatable  # only technical controls may automate
]
COLLECTORS = ("crawler@0.1.0", "cli@0.1.0", PERSON)
OUTCOMES = (None, "pass", "fail", "error")
DECISION_KINDS = (None, "attestation", "verification")
STATUSES = ("implemented", "partially_implemented", "not_implemented")
FRESHNESS = {  # valid_until for each state at AS_OF
    "fresh": AS_OF + timedelta(days=60),
    "expiring": AS_OF + timedelta(days=3),
    "stale": AS_OF - timedelta(days=1),
}


def control(kind, automatable) -> Control:
    return Control(
        id=ids.control_id("VC-001"),
        title="t",
        summary="Invented for the tests.",
        kind=kind,
        automatable=automatable,
        scope_level=ScopeLevel.SYSTEM,
        tenant="kestrel",
        source=Source.SYNTHETIC,
    )


def menu():
    """Every evidence shape: kind, collector, outcome, decision kind, status and freshness."""
    for kind, collector, outcome, decision, status, fresh in itertools.product(
        EvidenceKind, COLLECTORS, OUTCOMES, DECISION_KINDS, STATUSES, FRESHNESS
    ):
        extra = {}
        if outcome:
            extra["outcome"] = outcome
        if decision:
            extra["decision_kind"] = decision
        yield evidence(
            "VC-001",
            kind,
            collector=collector,
            collected_at=EARLIER,
            valid_until=FRESHNESS[fresh],
            status=status,
            **extra,
        )


def is_verification_by_a_person(ev) -> bool:
    content = ev.content
    return (
        ev.kind is EvidenceKind.ATTESTATION
        and content.get("decision_kind") == "verification"
        and ev.collector.startswith("person:")
        and ev.valid_until >= AS_OF
    )


MANUAL = [(kind, automatable) for kind, automatable in CONTROLS if not automatable]
EVIDENCE = list(menu())
NO_VERIFICATION = [e for e in EVIDENCE if not is_verification_by_a_person(e)]


def implemented(control_, items) -> bool:
    result = decide(control_, SYS, items, AS_OF)
    return result.status is ImplementationStatus.IMPLEMENTED


@pytest.mark.parametrize(("kind", "automatable"), MANUAL)
def test_one_piece_of_evidence_without_a_verification_never_implements_a_manual_control(
    kind, automatable
):
    c = control(kind, automatable)
    assert not [e for e in NO_VERIFICATION if implemented(c, [e])]


@pytest.mark.parametrize(("kind", "automatable"), MANUAL)
def test_pairs_of_evidence_without_a_verification_never_implement_a_manual_control(
    kind, automatable
):
    c = control(kind, automatable)
    # Pairs of distinct shapes, thinned to every 7th item so the suite stays quick.
    sample = NO_VERIFICATION[::7]
    for a, b in itertools.combinations(sample, 2):
        assert not implemented(c, [a, b])


def test_the_exhaustive_menu_covers_every_kind_collector_outcome_and_freshness():
    assert {e.kind for e in EVIDENCE} == set(EvidenceKind)
    assert {e.collector for e in EVIDENCE} == set(COLLECTORS)
    assert len(EVIDENCE) == len(EvidenceKind) * len(COLLECTORS) * len(OUTCOMES) * len(
        DECISION_KINDS
    ) * len(STATUSES) * len(FRESHNESS)


def test_a_verification_decision_by_a_person_can_implement_a_manual_control():
    c = control(ControlKind.ORGANISATIONAL, False)
    verifications = [e for e in EVIDENCE if is_verification_by_a_person(e)]
    assert verifications
    assert any(implemented(c, [e]) for e in verifications)
    for e in verifications:
        result = decide(c, SYS, [e], AS_OF)
        if result.status is ImplementationStatus.IMPLEMENTED:
            assert result.level is AssuranceLevel.L4_VERIFIED
            assert result.assessor == PERSON


@pytest.mark.parametrize(("kind", "automatable"), CONTROLS)
def test_nothing_but_a_verification_ever_reaches_l4(kind, automatable):
    c = control(kind, automatable)
    for e in NO_VERIFICATION:
        assert decide(c, SYS, [e], AS_OF).level < AssuranceLevel.L4_VERIFIED


def test_an_automated_collector_pretending_to_verify_is_ignored():
    c = control(ControlKind.ORGANISATIONAL, False)
    fake = evidence(
        "VC-001",
        EvidenceKind.ATTESTATION,
        collector="crawler@0.1.0",
        decision_kind="verification",
        status="implemented",
    )
    assert not implemented(c, [fake])


def test_a_manual_control_never_reaches_l3_from_automated_evidence_alone():
    c = control(ControlKind.ORGANISATIONAL, False)
    automated = [e for e in EVIDENCE if not e.collector.startswith("person:")]
    for e in automated:
        assert decide(c, SYS, [e], AS_OF).level < AssuranceLevel.L3_TESTED
