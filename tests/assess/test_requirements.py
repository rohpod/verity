from datetime import date

from assess_support import (
    AS_OF,
    ORG,
    PROV,
    SYS,
    applies,
    attestation,
    automated_result,
    control,
    evidence,
    maps,
    status_of,
    technical,
    verification,
    world,
)
from verity_core.assess.requirements import (
    AUTOMATED_ONLY,
    IN_HOUSE_ONLY,
    NEVER_MAPPED,
    PARTIAL_ONLY,
    REVIEWED_NO_CONTROL,
    ROLLUP,
    RequirementState,
)
from verity_core.graph.traversals import Resolution
from verity_core.model.edges import PlainEdge
from verity_core.model.enums import (
    AppliesCondition,
    EdgeType,
    EvidenceKind,
    ScopeLevel,
    StrmType,
    Sufficiency,
)
from verity_core.rules.status import ApplicabilityStatus

R = RequirementState
FULL, PARTIAL = Sufficiency.FULL, Sufficiency.PARTIAL


def one(controls, mappings, items=(), *, req="art1", **kw):
    graph = world(
        controls=controls,
        requirements=[req],
        mappings=mappings,
        applications=[applies(req)],
        evidence_items=items,
        **kw,
    )
    return status_of(graph, req)


# 1. every row dropped out
def test_row_1_in_house_models_only_make_a_provider_requirement_not_applicable():
    s = one([control("VC-050", scope=ScopeLevel.PROVIDER)], [maps("art1", "VC-050")])
    assert (s.state, s.reason) == (R.NOT_APPLICABLE, IN_HOUSE_ONLY)


def test_row_1_does_not_apply_when_another_control_still_resolves():
    controls = [control("VC-050", scope=ScopeLevel.PROVIDER), control("VC-001")]
    s = one(controls, [maps("art1", "VC-050"), maps("art1", "VC-001")], [verification("VC-001")])
    assert s.state is R.SATISFIED  # the provider control dropped out and does not count


# 2. parents
def parent_world(child_items=(), child_controls=("VC-001",), extra_children=()):
    controls = [control(c) for c in child_controls]
    children = ["art9-2a", *extra_children]
    mappings = [maps("art9-2a", code) for code in child_controls]
    mappings += [maps(c, child_controls[0]) for c in extra_children]
    graph = world(
        controls=controls,
        requirements=["art9", *children],
        mappings=mappings,
        applications=[applies(r) for r in ["art9", *children]],
        evidence_items=child_items,
        extra_edges=[
            PlainEdge(
                src=f"req:euaia:{c}", dst="req:euaia:art9", type=EdgeType.PART_OF, **_common()
            )
            for c in children
        ],
    )
    return graph


def _common():
    from assess_support import COMMON

    return COMMON


def test_row_2_a_parent_is_partially_addressed_when_a_child_is():
    # The child maps two controls and one is met, so it is partially addressed.
    graph = parent_world([verification("VC-001")], child_controls=("VC-001", "VC-002"))
    assert status_of(graph, "art9-2a").state is R.PARTIALLY_ADDRESSED
    parent = status_of(graph, "art9")
    assert (parent.state, parent.reason) == (R.PARTIALLY_ADDRESSED, ROLLUP)


def test_row_2_a_parent_is_never_satisfied_even_when_every_child_is():
    graph = parent_world([verification("VC-001")])
    assert status_of(graph, "art9-2a").state is R.SATISFIED
    parent = status_of(graph, "art9")
    assert (parent.state, parent.reason) == (R.PARTIALLY_ADDRESSED, ROLLUP)


def test_row_2_a_parent_is_not_met_when_no_child_is_addressed():
    parent = status_of(parent_world(), "art9")
    assert (parent.state, parent.reason) == (R.NOT_MET, ROLLUP)


def test_row_2_a_parent_whose_children_are_all_unmapped_is_not_met():
    graph = world(
        requirements=["art9", "art9-2a"],
        applications=[applies("art9"), applies("art9-2a")],
        extra_edges=[
            PlainEdge(
                src="req:euaia:art9-2a", dst="req:euaia:art9", type=EdgeType.PART_OF, **_common()
            )
        ],
    )
    assert status_of(graph, "art9").state is R.NOT_MET
    assert status_of(graph, "art9-2a").state is R.NOT_ADDRESSED


def test_row_2_a_child_that_does_not_apply_is_left_out_of_the_rollup():
    graph = world(
        controls=[control("VC-001")],
        requirements=["art9", "art9-2a"],
        mappings=[maps("art9-2a", "VC-001")],
        applications=[applies("art9")],  # the child has no APPLIES_TO
        evidence_items=[verification("VC-001")],
        extra_edges=[
            PlainEdge(
                src="req:euaia:art9-2a", dst="req:euaia:art9", type=EdgeType.PART_OF, **_common()
            )
        ],
    )
    assert status_of(graph, "art9").state is R.NOT_MET


def test_row_2_a_parent_with_its_own_mapping_is_judged_on_that_mapping():
    graph = world(
        controls=[control("VC-001")],
        requirements=["art26", "art26-2"],
        mappings=[maps("art26", "VC-001")],
        applications=[applies("art26"), applies("art26-2")],
        evidence_items=[verification("VC-001")],
        extra_edges=[
            PlainEdge(
                src="req:euaia:art26-2", dst="req:euaia:art26", type=EdgeType.PART_OF, **_common()
            )
        ],
    )
    assert status_of(graph, "art26").state is R.SATISFIED


# 3. no usable mapping
def test_row_3_never_mapped():
    s = one([], [])
    assert (s.state, s.reason) == (R.NOT_ADDRESSED, NEVER_MAPPED)


def test_row_3_reviewed_and_found_to_have_no_control():
    s = one([control("VC-001")], [maps("art1", "VC-001", strm=StrmType.NO_RELATIONSHIP)])
    assert (s.state, s.reason) == (R.NOT_ADDRESSED, REVIEWED_NO_CONTROL)


def test_row_3_a_no_relationship_mapping_never_helps_a_control_that_is_met():
    controls = [control("VC-001"), control("VC-002")]
    mappings = [
        maps("art1", "VC-001", strm=StrmType.NO_RELATIONSHIP),
        maps("art1", "VC-002"),
    ]
    s = one(controls, mappings, [verification("VC-001")])
    assert s.state is R.NOT_MET  # VC-001 is not a usable mapping, and VC-002 has no evidence


# 4. satisfied
def test_row_4_satisfied_when_the_full_set_is_met_and_one_control_is_not_automatable():
    controls = [control("VC-001"), control("VC-002")]
    s = one(
        controls,
        [maps("art1", "VC-001"), maps("art1", "VC-002")],
        [verification("VC-001")] + [verification("VC-002")],
    )
    assert (s.state, s.reason) == (R.SATISFIED, None)


def test_row_4_a_document_alone_is_only_partial_so_it_does_not_satisfy():
    doc = evidence("VC-001", EvidenceKind.DOCUMENT_REF, path="evidence/x.md")
    s = one([control("VC-001")], [maps("art1", "VC-001")], [doc])
    assert s.state is R.NOT_MET  # a document is only Partially implemented, so not met


def test_row_4_every_control_in_the_full_set_must_be_met():
    controls = [control("VC-001"), control("VC-002")]
    s = one(controls, [maps("art1", "VC-001"), maps("art1", "VC-002")], [verification("VC-001")])
    assert (s.state, s.reason) == (R.PARTIALLY_ADDRESSED, PARTIAL_ONLY)


def test_row_4_stale_evidence_means_it_is_not_satisfied():
    from datetime import timedelta

    old = verification("VC-001", valid_until=AS_OF - timedelta(days=1))
    s = one([control("VC-001")], [maps("art1", "VC-001")], [old])
    assert s.state is R.NOT_MET


# 5. the guardrail
def test_row_5_d2_an_empty_full_set_is_never_satisfied():
    s = one(
        [control("VC-001")],
        [maps("art1", "VC-001", strm=StrmType.INTERSECTS_WITH, sufficiency=PARTIAL, strength=5)],
        [verification("VC-001")],
    )
    assert (s.state, s.reason) == (R.PARTIALLY_ADDRESSED, PARTIAL_ONLY)


def test_row_5_an_art_50_1_style_requirement_at_l3_stops_at_automated_only():
    # One automatable control, tested and passing at L3. Nothing is non-automatable or at L4.
    s = one(
        [technical("VC-012")],
        [maps("art50-1", "VC-012")],
        [automated_result("VC-012", "pass")],
        req="art50-1",
    )
    assert (s.state, s.reason) == (R.PARTIALLY_ADDRESSED, AUTOMATED_ONLY)


def test_row_5_two_automated_controls_still_stop_at_automated_only():
    controls = [technical("VC-012"), technical("VC-013")]
    mappings = [maps("art12", "VC-012"), maps("art12", "VC-013")]
    items = [automated_result("VC-012", "pass"), automated_result("VC-013", "pass")]
    s = one(controls, mappings, items, req="art12")
    assert (s.state, s.reason) == (R.PARTIALLY_ADDRESSED, AUTOMATED_ONLY)


def test_row_5_a_person_verifying_an_automatable_control_lifts_the_guardrail():
    s = one(
        [technical("VC-012")],
        [maps("art50-1", "VC-012")],
        [verification("VC-012")],
        req="art50-1",
    )
    assert s.state is R.SATISFIED


def test_row_5_a_non_automatable_control_in_the_full_set_lifts_the_guardrail():
    controls = [technical("VC-012"), control("VC-014")]
    mappings = [maps("art50-1", "VC-012"), maps("art50-1", "VC-014")]
    items = [automated_result("VC-012", "pass"), verification("VC-014")]
    s = one(controls, mappings, items, req="art50-1")
    assert s.state is R.SATISFIED


def test_row_5_a_non_automatable_control_outside_the_full_set_does_not_lift_it():
    controls = [technical("VC-012"), control("VC-014")]
    mappings = [
        maps("art50-1", "VC-012"),
        maps("art50-1", "VC-014", strm=StrmType.INTERSECTS_WITH, sufficiency=PARTIAL, strength=4),
    ]
    items = [automated_result("VC-012", "pass"), verification("VC-014")]
    s = one(controls, mappings, items, req="art50-1")
    assert (s.state, s.reason) == (R.PARTIALLY_ADDRESSED, AUTOMATED_ONLY)


# 6 and 7
def test_row_6_at_least_one_mapped_control_met_is_partially_addressed():
    controls = [control("VC-001"), control("VC-002")]
    mappings = [maps("art1", "VC-001"), maps("art1", "VC-002")]
    s = one(controls, mappings, [verification("VC-002")])
    assert (s.state, s.reason) == (R.PARTIALLY_ADDRESSED, PARTIAL_ONLY)


def test_row_6_a_met_partial_mapping_alone_is_partially_addressed():
    mappings = [
        maps("art1", "VC-001", strm=StrmType.INTERSECTS_WITH, sufficiency=PARTIAL, strength=5)
    ]
    s = one([control("VC-001")], mappings, [verification("VC-001")])
    assert (s.state, s.reason) == (R.PARTIALLY_ADDRESSED, PARTIAL_ONLY)


def test_row_7_nothing_met_is_not_met():
    controls = [control("VC-001"), control("VC-002")]
    s = one(controls, [maps("art1", "VC-001"), maps("art1", "VC-002")], [attestation("VC-001")])
    assert (s.state, s.reason) == (R.NOT_MET, None)


def test_row_7_a_failing_control_is_not_met():
    s = one([technical("VC-012")], [maps("art1", "VC-012")], [automated_result("VC-012", "fail")])
    assert s.state is R.NOT_MET


# targets: D13 and provider_unknown
def provider_control():
    return control("VC-050", scope=ScopeLevel.PROVIDER)


def test_d13_a_known_provider_answers_for_a_provider_level_control():
    s = one(
        [provider_control()],
        [maps("art1", "VC-050")],
        [verification("VC-050", scope=PROV)],
        models=("known",),
    )
    assert s.state is R.SATISFIED
    assert [(t.scope_id, t.resolution) for t in s.targets] == [
        (PROV, Resolution.INHERITED_PROVIDER)
    ]


def test_d13_evidence_for_the_system_does_not_answer_a_provider_control():
    s = one(
        [provider_control()],
        [maps("art1", "VC-050")],
        [verification("VC-050", scope=SYS)],
        models=("known",),
    )
    assert s.state is R.NOT_MET


def test_provider_unknown_is_unmet_and_never_not_applicable():
    s = one([provider_control()], [maps("art1", "VC-050")], models=("unknown",))
    assert s.state is R.NOT_MET
    assert [(t.scope_id, t.resolution) for t in s.targets] == [(None, Resolution.PROVIDER_UNKNOWN)]


def test_provider_unknown_with_no_model_at_all_is_unmet():
    s = one([provider_control()], [maps("art1", "VC-050")], models=())
    assert s.state is R.NOT_MET


def test_a_known_provider_does_not_hide_an_unknown_one():
    s = one(
        [provider_control()],
        [maps("art1", "VC-050")],
        [verification("VC-050", scope=PROV)],
        models=("known", "unknown"),
    )
    assert s.state is R.NOT_MET


def test_an_in_house_model_next_to_a_known_provider_is_judged_on_the_provider():
    s = one(
        [provider_control()],
        [maps("art1", "VC-050")],
        [verification("VC-050", scope=PROV)],
        models=("in_house", "known"),
    )
    assert s.state is R.SATISFIED


def test_an_organisation_control_is_answered_by_the_organisation():
    s = one(
        [control("VC-001", scope=ScopeLevel.ORGANISATION)],
        [maps("art1", "VC-001")],
        [verification("VC-001", scope=ORG)],
    )
    assert s.state is R.SATISFIED
    assert s.targets[0].resolution is Resolution.INHERITED_ORG


def test_a_requirement_aimed_at_the_organisation_resolves_a_system_control_for_the_system():
    graph = world(
        controls=[control("VC-014")],
        requirements=["a1"],
        mappings=[maps("a1", "VC-014")],
        applications=[applies("a1", target=ORG)],
        evidence_items=[verification("VC-014", scope=SYS)],
    )
    assert status_of(graph, "a1").state is R.SATISFIED


# the applicability carried along
def test_the_status_carries_the_strongest_applicability():
    def got(**edge):
        graph = world(requirements=["a1"], applications=[applies("a1", **edge)])
        return status_of(graph, "a1").applicability

    assert got() is ApplicabilityStatus.IN_FORCE
    assert got(in_force_from=date(2027, 1, 1)) is ApplicabilityStatus.UPCOMING
    assert got(in_force_from=date(2026, 1, 1)) is ApplicabilityStatus.IN_FORCE
    conditional = got(condition=AppliesCondition.LEGACY_SIGNIFICANT_CHANGE)
    assert conditional is ApplicabilityStatus.CONDITIONAL


def test_the_requirement_applies_in_two_roles_and_is_judged_once():
    from verity_core.model.enums import Role

    graph = world(
        controls=[control("VC-001")],
        requirements=["a1"],
        mappings=[maps("a1", "VC-001")],
        applications=[applies("a1", role=Role.PROVIDER), applies("a1", role=Role.DEPLOYER)],
        evidence_items=[verification("VC-001")],
    )
    assert status_of(graph, "a1").state is R.SATISFIED
