"""The section E traversals as executable tests, for the three use cases.

All five traversals, for all three use cases. The estate (`estate.py`) is fictional and
its mappings are placeholders, so these tests check graph behaviour, not legal content.
"""

import dataclasses
from datetime import timedelta

import estate as E
import pytest
from factories import COMMON, make_edge
from factories import evidence as make_evidence
from verity_core.graph.integrity import check_integrity
from verity_core.graph.loader import build_graph
from verity_core.graph.traversals import (
    DerivedLink,
    Resolution,
    audit_trail,
    crosswalk,
    obligations_for,
    provider_impact,
    stale_by_change,
)
from verity_core.model import ids
from verity_core.model.enums import (
    AssuranceLevel,
    EdgeType,
    EvidenceKind,
    ImplementationStatus,
    ModelOrigin,
    Role,
    Source,
    StrmType,
)
from verity_core.model.nodes import Model, Person

R = Resolution
GPT = ids.model_id("gpt-class")


def project(rows):
    """What a row says, without the edge objects: easier to read in a failing test."""
    return [
        (
            r.requirement_id,
            r.role,
            r.control_id,
            r.resolution,
            r.provider_id,
            r.assessment_id,
            len(r.evidence_ids),
        )
        for r in rows
    ]


def test_the_estate_is_sound(estate_graph):
    assert check_integrity(estate_graph) == []


# --- 1. What applies to system S, and what proves it? -------------------------------------

ART4_ROWS = [  # organisation-level, so it reaches every system, once per role (ADR 0012 / C1)
    (
        E.ART4,
        Role.DEPLOYER,
        E.VC_AI_LITERACY,
        R.INHERITED_ORG,
        None,
        E.ca(E.VC_AI_LITERACY, E.ORG),
        0,
    ),
    (
        E.ART4,
        Role.PROVIDER,
        E.VC_AI_LITERACY,
        R.INHERITED_ORG,
        None,
        E.ca(E.VC_AI_LITERACY, E.ORG),
        0,
    ),
]

OBLIGATIONS = {
    # Art. 50(1) is answered directly, with automated evidence. The supplier control is the
    # provider's, found through the model.
    E.SUPPORT: [
        *ART4_ROWS,
        (
            E.ART50_1,
            Role.PROVIDER,
            E.VC_DISCLOSURE,
            R.DIRECT,
            None,
            E.ca(E.VC_DISCLOSURE, E.SUPPORT),
            1,
        ),
        (
            E.ISO_A10_3,
            Role.ANY,
            E.VC_SUPPLIER_DPA,
            R.INHERITED_PROVIDER,
            E.BEDROCK,
            E.ca(E.VC_SUPPLIER_DPA, E.BEDROCK),
            1,
        ),
    ],
    # Art. 9 has no control of its own (unmapped); its sub-clause's bias test has an assessment
    # but no evidence (a gap); human oversight is signed off and has a person's attestation plus
    # a crawler snapshot; the in-house model has no provider.
    E.TALENT: [
        (E.ART14, Role.PROVIDER, E.VC_OVERSIGHT, R.DIRECT, None, E.ca(E.VC_OVERSIGHT, E.TALENT), 2),
        *ART4_ROWS,
        (E.ART9, Role.PROVIDER, None, R.UNMAPPED, None, None, 0),
        (
            E.ART9_2A,
            Role.PROVIDER,
            E.VC_BIAS_TEST,
            R.DIRECT,
            None,
            E.ca(E.VC_BIAS_TEST, E.TALENT),
            0,
        ),
        (E.ISO_A10_3, Role.ANY, E.VC_SUPPLIER_DPA, R.NOT_APPLICABLE, None, None, 0),
    ],
    # The DPA control resolves to the provider's assessment, which exists but has no evidence.
    E.CONTRACT: [
        *ART4_ROWS,
        (
            E.ISO_A10_3,
            Role.ANY,
            E.VC_SUPPLIER_DPA,
            R.INHERITED_PROVIDER,
            E.OPENAI,
            E.ca(E.VC_SUPPLIER_DPA, E.OPENAI),
            0,
        ),
        (E.ISO_A7_4, Role.ANY, E.VC_EGRESS, R.DIRECT, None, E.ca(E.VC_EGRESS, E.CONTRACT), 2),
    ],
}


@pytest.mark.parametrize("system", OBLIGATIONS, ids=lambda s: s.split(":")[1])
def test_obligations_for_each_use_case(estate_graph, system):
    assert project(obligations_for(estate_graph, system)) == OBLIGATIONS[system]


def test_org_level_requirements_reach_every_system_but_only_by_role_rows(estate_graph):
    for system in OBLIGATIONS:
        art4 = [r for r in obligations_for(estate_graph, system) if r.requirement_id == E.ART4]
        assert {r.role for r in art4} == {Role.PROVIDER, Role.DEPLOYER}
        assert {r.applies_to for r in art4} == {E.ORG}


def test_rows_carry_the_mapping_for_the_ui(estate_graph):
    row = next(r for r in obligations_for(estate_graph, E.SUPPORT) if r.requirement_id == E.ART50_1)
    assert row.mapping.strength == 8 and row.mapping.rationale
    assert row.applies_to == E.SUPPORT
    assert row.evidence_ids and row.evidence_ids[0].startswith("ev:")


def test_a_system_cannot_see_another_systems_rows(estate_graph):
    mine = {r.assessment_id for r in obligations_for(estate_graph, E.SUPPORT)}
    assert E.ca(E.VC_OVERSIGHT, E.TALENT) not in mine
    assert E.ca(E.VC_SUPPLIER_DPA, E.OPENAI) not in mine


def test_no_relationship_mappings_add_no_control(estate_graph):
    # ART25 maps to the supplier control only as no_relationship, so it never appears as a row.
    assert E.ART25 not in {
        r.requirement_id for s in OBLIGATIONS for r in obligations_for(estate_graph, s)
    }


def test_obligations_need_an_ai_system(estate_graph):
    for bad in (E.ORG, E.BEDROCK, "sys:nope"):
        with pytest.raises(ValueError, match="AISystem"):
            obligations_for(estate_graph, bad)


def test_obligations_ignore_a_closed_applies_to_edge(estate, clock):
    from verity_core.model.enums import EdgeType

    estate.close_edge(
        E.ART50_1, EdgeType.APPLIES_TO, E.SUPPORT, valid_to=clock.now, qualifier="provider"
    )
    assert E.ART50_1 not in {
        r.requirement_id for r in obligations_for(estate.load_graph(), E.SUPPORT)
    }


def test_obligations_without_an_organisation_still_work(estate_graph):
    graph = estate_graph.copy()
    graph.remove_node(E.ORG)
    rows = obligations_for(graph, E.SUPPORT)
    assert E.ART4 not in {r.requirement_id for r in rows}  # its APPLIES_TO edges went with the org


def test_the_unmapped_requirement_is_a_row_not_a_silent_drop(estate_graph):
    unmapped = [r for r in obligations_for(estate_graph, E.TALENT) if r.resolution is R.UNMAPPED]
    assert [r.requirement_id for r in unmapped] == [E.ART9]
    assert unmapped[0].mapping is None and unmapped[0].evidence_ids == ()


def supplier_row(graph):
    return [
        (r.resolution, r.provider_id, r.assessment_id)
        for r in obligations_for(graph, E.CONTRACT)
        if r.requirement_id == E.ISO_A10_3
    ]


def test_a_third_party_model_with_no_provider_is_a_gap_not_not_applicable(estate_graph):
    graph = estate_graph.copy()
    graph.remove_edge(GPT, E.OPENAI, (EdgeType.PROVIDED_BY, None))
    assert supplier_row(graph) == [(R.PROVIDER_UNKNOWN, None, None)]


def test_a_system_with_no_recorded_model_is_a_gap_not_not_applicable(estate_graph):
    graph = estate_graph.copy()
    graph.remove_edge(E.CONTRACT, GPT, (EdgeType.USES_MODEL, None))
    assert supplier_row(graph) == [(R.PROVIDER_UNKNOWN, None, None)]


def test_a_known_provider_does_not_hide_a_second_model_with_no_provider(estate_graph):
    graph = estate_graph.copy()
    orphan = Model(id=ids.model_id("orphan"), name="X", origin=ModelOrigin.THIRD_PARTY, **COMMON)
    graph.add_node(orphan.id, record=orphan)
    used = make_edge(EdgeType.USES_MODEL, E.CONTRACT, orphan.id)
    graph.add_edge(E.CONTRACT, orphan.id, key=(EdgeType.USES_MODEL, None), record=used)
    assert {r for r, _, _ in supplier_row(graph)} == {R.INHERITED_PROVIDER, R.PROVIDER_UNKNOWN}


def test_only_in_house_models_are_not_applicable(estate_graph):
    (row,) = [r for r in obligations_for(estate_graph, E.TALENT) if r.requirement_id == E.ISO_A10_3]
    assert row.resolution is R.NOT_APPLICABLE


# --- 5. Audit trail ------------------------------------------------------------------------


def test_audit_trail_support_assistant_has_automated_evidence_and_no_verifier(estate_graph):
    trail = audit_trail(estate_graph, E.ART50_1, E.SUPPORT)
    (link,) = trail.links
    assert (link.control_id, link.resolution) == (E.VC_DISCLOSURE, R.DIRECT)
    assert link.status is ImplementationStatus.IMPLEMENTED
    assert link.assurance_level is AssuranceLevel.L3_TESTED
    assert link.assessed_by is None and link.signoff_source is None
    (evidence,) = link.evidence
    assert evidence.kind is EvidenceKind.AUTOMATED_TEST
    assert evidence.collector == "crawler@0.1.0"
    assert evidence.sha256 == estate_graph.nodes[evidence.evidence_id]["record"].sha256
    assert link.mapping.strength == 8


def test_audit_trail_talent_screening_is_verified_by_a_named_person_and_labelled_simulated(
    estate_graph,
):
    (link,) = audit_trail(estate_graph, E.ART14, E.TALENT).links
    assert link.assurance_level is AssuranceLevel.L4_VERIFIED
    assert link.assessed_by == E.VERIFIER
    assert link.signoff_source is Source.SIMULATED  # D11
    assert link.assessment_source is Source.SIMULATED
    snapshot, attestation = link.evidence  # oldest first
    assert snapshot.kind is EvidenceKind.CONFIG_SNAPSHOT and snapshot.collector == "crawler@0.1.0"
    assert attestation.kind is EvidenceKind.ATTESTATION and attestation.collector == E.VERIFIER
    assert attestation.source is Source.SIMULATED


def test_audit_trail_names_the_assessor_when_there_are_two_assessed_edges(estate):
    other = Person(id=ids.person_id("a-aaa"), name="Sorts first", **COMMON)
    estate.upsert_node(other)
    estate.upsert_edge(make_edge(EdgeType.ASSESSED, other.id, E.ca(E.VC_OVERSIGHT, E.TALENT)))
    (link,) = audit_trail(estate.load_graph(), E.ART14, E.TALENT).links
    assert link.assessed_by == E.VERIFIER
    assert link.signoff_source is Source.SIMULATED


def test_audit_trail_talent_screening_bias_test_is_an_assessment_with_no_proof(estate_graph):
    (link,) = audit_trail(estate_graph, E.ART9_2A, E.TALENT).links
    assert link.status is ImplementationStatus.NOT_IMPLEMENTED
    assert link.assessment_id == E.ca(E.VC_BIAS_TEST, E.TALENT)
    assert link.evidence == () and link.assessed_by is None


def test_audit_trail_contract_insights_follows_the_provider_and_shows_the_gap(estate_graph):
    (link,) = audit_trail(estate_graph, E.ISO_A10_3, E.CONTRACT).links
    assert link.resolution is R.INHERITED_PROVIDER and link.provider_id == E.OPENAI
    assert link.assessment_id == E.ca(E.VC_SUPPLIER_DPA, E.OPENAI)
    assert link.status is ImplementationStatus.NOT_IMPLEMENTED
    assert link.evidence == ()  # the missing DPA is an explicit empty link


def test_audit_trail_provider_evidence_is_about_the_provider(estate_graph):
    (link,) = audit_trail(estate_graph, E.ISO_A10_3, E.SUPPORT).links
    assert link.provider_id == E.BEDROCK
    (evidence,) = link.evidence
    assert evidence.kind is EvidenceKind.DOCUMENT_REF and evidence.collector == E.VERIFIER


def test_audit_trail_in_house_model_is_not_applicable_rather_than_missing(estate_graph):
    (link,) = audit_trail(estate_graph, E.ISO_A10_3, E.TALENT).links
    assert link.resolution is R.NOT_APPLICABLE
    assert link.assessment_id is None and link.status is None and link.evidence == ()


def test_audit_trail_for_an_organisation_and_a_provider_scope(estate_graph):
    (org_link,) = audit_trail(estate_graph, E.ART4, E.ORG).links
    assert org_link.resolution is R.DIRECT
    assert org_link.assessment_id == E.ca(E.VC_AI_LITERACY, E.ORG)
    (provider_link,) = audit_trail(estate_graph, E.ISO_A10_3, E.OPENAI).links
    assert provider_link.resolution is R.DIRECT and provider_link.provider_id is None
    # A system-level control asked of an organisation is not that organisation's to answer.
    (other,) = audit_trail(estate_graph, E.ART50_1, E.ORG).links
    assert other.resolution is R.NOT_APPLICABLE


def test_audit_trail_unmapped_and_no_relationship_requirements_give_an_empty_link(estate_graph):
    for requirement in (E.ART9, E.ART25):
        (link,) = audit_trail(estate_graph, requirement, E.TALENT).links
        assert link.resolution is R.UNMAPPED
        assert link.control_id is None and link.evidence == ()


def test_audit_trail_evidence_is_ordered_by_collection_time(estate):
    from datetime import timedelta

    from factories import T0, make_edge
    from factories import evidence as make_evidence
    from verity_core.model.enums import EdgeType

    later = make_evidence(
        subject=E.SUPPORT,
        content={"banner_shown": True},
        collected_at=T0 + timedelta(days=1),
        valid_until=T0 + timedelta(days=31),
    )
    earlier = make_evidence(
        subject=E.SUPPORT,
        content={"banner_shown": False},
        collected_at=T0 - timedelta(days=1),
        valid_until=T0 + timedelta(days=29),
    )
    for node in (later, earlier):  # written newest first, to prove the order is not insertion order
        estate.upsert_node(node)
        estate.upsert_edge(make_edge(EdgeType.ABOUT, node.id, E.SUPPORT))
        estate.upsert_edge(make_edge(EdgeType.SUPPORTS, node.id, E.ca(E.VC_DISCLOSURE, E.SUPPORT)))
    (link,) = audit_trail(estate.load_graph(), E.ART50_1, E.SUPPORT).links
    stamps = [e.collected_at for e in link.evidence]
    assert len(stamps) == 3 and stamps == sorted(stamps)


def test_audit_trail_needs_a_requirement_and_a_scope(estate_graph):
    with pytest.raises(ValueError, match="Requirement"):
        audit_trail(estate_graph, E.SUPPORT, E.SUPPORT)
    with pytest.raises(ValueError, match="AISystem"):
        audit_trail(estate_graph, E.ART4, E.VC_AI_LITERACY)
    with pytest.raises(ValueError):
        audit_trail(estate_graph, "req:nope:x", E.SUPPORT)


def test_traversals_work_on_a_graph_built_directly(estate_graph):
    nodes = [d["record"] for _, d in estate_graph.nodes(data=True)]
    edges = [d["record"] for _, _, d in estate_graph.edges(data=True)]
    rebuilt = build_graph(nodes, edges)
    assert project(obligations_for(rebuilt, E.TALENT)) == OBLIGATIONS[E.TALENT]


# --- 2. Impact of an incident at provider P -----------------------------------------------


def system_ids(impact):
    return [s.system_id for s in impact.systems]


def test_provider_impact_support_assistant_reaches_its_owner_risks_and_requirements(estate_graph):
    impact = provider_impact(estate_graph, E.BEDROCK)
    assert impact.assessment_ids == (E.ca(E.VC_SUPPLIER_DPA, E.BEDROCK),)
    (system,) = impact.systems
    assert system.system_id == E.SUPPORT
    assert system.model_ids == (ids.model_id("bedrock-fm"),)
    assert system.owner_ids == (E.SUPPORT_LEAD,)
    assert system.risk_ids == (E.RISK_SUPPORT,)
    assert system.requirement_ids == (E.ART50_1, E.ISO_A10_3)


def test_provider_impact_contract_insights_reaches_the_provider_scoped_assessment(estate_graph):
    impact = provider_impact(estate_graph, E.OPENAI)
    assert impact.assessment_ids == (E.ca(E.VC_SUPPLIER_DPA, E.OPENAI),)
    (system,) = impact.systems
    assert system.system_id == E.CONTRACT
    assert (system.owner_ids, system.risk_ids) == ((E.VERIFIER,), (E.RISK_CONTRACT,))
    assert system.requirement_ids == (E.ISO_A10_3, E.ISO_A7_4)


def test_provider_impact_never_reaches_a_system_with_an_in_house_model(estate_graph):
    reached = [
        s for p in (E.BEDROCK, E.OPENAI) for s in system_ids(provider_impact(estate_graph, p))
    ]
    assert E.TALENT not in reached
    assert sorted(reached) == [E.CONTRACT, E.SUPPORT]


def test_provider_impact_does_not_leak_between_providers(estate_graph):
    bedrock = provider_impact(estate_graph, E.BEDROCK)
    openai = provider_impact(estate_graph, E.OPENAI)
    assert E.CONTRACT not in system_ids(bedrock) and E.SUPPORT not in system_ids(openai)
    # Both systems share the supplier requirement, but that does not connect them.
    assert not set(bedrock.systems[0].owner_ids) & set(openai.systems[0].owner_ids)


def test_provider_impact_with_no_models_is_empty(estate_graph):
    graph = estate_graph.copy()
    graph.remove_node(ids.model_id("bedrock-fm"))
    impact = provider_impact(graph, E.BEDROCK)
    assert impact.systems == () and impact.assessment_ids == (E.ca(E.VC_SUPPLIER_DPA, E.BEDROCK),)


def test_provider_impact_needs_a_provider(estate_graph):
    for bad in (E.SUPPORT, "prov:nope"):
        with pytest.raises(ValueError, match="Provider"):
            provider_impact(estate_graph, bad)


# --- 3. Crosswalk --------------------------------------------------------------------------


def test_crosswalk_support_assistant_derived_link_takes_the_weaker_strength(estate_graph):
    (link,) = crosswalk(estate_graph, E.ART50_1, E.ISO)
    assert (link.via_control_id, link.target_requirement_id) == (E.VC_DISCLOSURE, E.ISO_A8_2)
    assert (link.left.strength, link.right.strength) == (8, 5)
    assert link.strength == 5
    # Both spokes are kept, with their own relationship types.
    assert link.left.strm is StrmType.SUBSET_OF and link.right.strm is StrmType.INTERSECTS_WITH


def test_a_derived_link_has_no_strm_type(estate_graph):
    (link,) = crosswalk(estate_graph, E.ART50_1, E.ISO)
    assert "strm" not in {f.name for f in dataclasses.fields(DerivedLink)}
    assert not hasattr(link, "strm")  # D6: composing two spokes gives no trustworthy type


def test_crosswalk_talent_screening_sub_clause_resolves_through_part_of(estate_graph):
    # ART9_2A maps to the bias control, which an ISO sub-clause (A.9.3, under A.9) also maps to.
    (link,) = crosswalk(estate_graph, E.ART9_2A, E.ISO)
    assert (link.via_control_id, link.target_requirement_id) == (E.VC_BIAS_TEST, E.ISO_A9_3)
    assert link.strength == 6


def test_crosswalk_works_in_both_directions_and_through_nested_clauses(estate_graph):
    (forward,) = crosswalk(estate_graph, E.ART14, E.ISO)
    assert (
        forward.target_requirement_id == E.ISO_A6_2_4
    )  # A.6.2.4 is under A.6, under the framework
    assert forward.strength == 7
    (back,) = crosswalk(estate_graph, E.ISO_A6_2_4, E.EUAIA)
    assert back.target_requirement_id == E.ART14 and back.strength == 7


def test_crosswalk_contract_insights_no_relationship_does_not_compose(estate_graph):
    # ART25 maps to the supplier control only as no_relationship, so it is not a related
    # requirement of the supplier clause.
    assert crosswalk(estate_graph, E.ISO_A10_3, E.EUAIA) == []
    # And a requirement whose own spoke is no_relationship has nothing to compose from.
    assert crosswalk(estate_graph, E.ART25, E.ISO) == []


def test_crosswalk_excludes_the_requirement_itself_and_other_frameworks(estate_graph):
    assert crosswalk(estate_graph, E.ART14, E.EUAIA) == []  # nothing else in the EU Act on VC-014
    assert all(
        link.target_requirement_id.startswith("req:iso42001:")
        for link in crosswalk(estate_graph, E.ART14, E.ISO)
    )


def test_crosswalk_stops_on_a_part_of_cycle(estate_graph):
    nodes = [d["record"] for _, d in estate_graph.nodes(data=True)]
    edges = [d["record"] for _, _, d in estate_graph.edges(data=True)]
    loop = make_edge(EdgeType.PART_OF, E.ISO_A9, E.ISO_A9_3)  # A.9.3 is under A.9, and now back
    graph = build_graph(nodes, [*edges, loop])
    assert crosswalk(graph, E.ART9_2A, E.EUAIA) == []  # walks the cycle once, finds no framework
    assert len(crosswalk(graph, E.ART9_2A, E.ISO)) == 1


def test_crosswalk_needs_a_requirement_and_a_framework(estate_graph):
    with pytest.raises(ValueError, match="Requirement"):
        crosswalk(estate_graph, E.SUPPORT, E.ISO)
    with pytest.raises(ValueError, match="Framework"):
        crosswalk(estate_graph, E.ART14, E.ART4)


# --- 4. Evidence made stale by a change ----------------------------------------------------


def evidence_ids(graph, subject, kind):
    return [
        n
        for n, d in graph.nodes(data=True)
        if d["record"].type.value == "Evidence"
        and d["record"].subject == subject
        and d["record"].kind is kind
    ]


def test_stale_support_assistant_earlier_evidence_is_hit_and_later_evidence_is_not(estate):
    graph = estate.load_graph()
    (test_run,) = evidence_ids(graph, E.SUPPORT, EvidenceKind.AUTOMATED_TEST)
    impact = stale_by_change(graph, E.CHG_SUPPORT)
    assert [(s.evidence_id, s.resource_id) for s in impact.evidence] == [(test_run, E.RES_SUPPORT)]
    assert impact.assessment_ids == (E.ca(E.VC_DISCLOSURE, E.SUPPORT),)

    # The crawler collects again after the change: the new evidence is fresh, the old stays stale.
    recollected = make_evidence(
        subject=E.SUPPORT,
        content={"banner_shown": True, "rechecked": True},
        collected_at=E.CHANGE_DETECTED_AT + timedelta(hours=1),
        valid_until=E.CHANGE_DETECTED_AT + timedelta(days=30),
    )
    estate.upsert_node(recollected)
    for edge in (
        make_edge(EdgeType.ABOUT, recollected.id, E.SUPPORT),
        make_edge(EdgeType.SUPPORTS, recollected.id, E.ca(E.VC_DISCLOSURE, E.SUPPORT)),
        make_edge(EdgeType.COLLECTED_FROM, recollected.id, E.RES_SUPPORT),
    ):
        estate.upsert_edge(edge)
    after = stale_by_change(estate.load_graph(), E.CHG_SUPPORT)
    assert [s.evidence_id for s in after.evidence] == [test_run]


def test_evidence_collected_at_the_moment_of_the_change_is_not_stale(estate):
    same_run = make_evidence(
        subject=E.SUPPORT,
        content={"same": "run"},
        collected_at=E.CHANGE_DETECTED_AT,
        valid_until=E.CHANGE_DETECTED_AT + timedelta(days=30),
    )
    estate.upsert_node(same_run)
    estate.upsert_edge(make_edge(EdgeType.COLLECTED_FROM, same_run.id, E.RES_SUPPORT))
    stale = stale_by_change(estate.load_graph(), E.CHG_SUPPORT)
    assert same_run.id not in [s.evidence_id for s in stale.evidence]  # collected_at < detected_at


def test_stale_talent_screening_returns_the_assessment_but_spares_the_attestation(estate_graph):
    (snapshot,) = evidence_ids(estate_graph, E.TALENT, EvidenceKind.CONFIG_SNAPSHOT)
    (attestation,) = evidence_ids(estate_graph, E.TALENT, EvidenceKind.ATTESTATION)
    impact = stale_by_change(estate_graph, E.CHG_TALENT)
    assert [s.evidence_id for s in impact.evidence] == [snapshot]
    assert attestation not in [s.evidence_id for s in impact.evidence]  # a person, not a resource
    assert impact.assessment_ids == (E.ca(E.VC_OVERSIGHT, E.TALENT),)  # the CA is returned


def test_stale_contract_insights_hits_config_evidence_but_not_the_document(estate_graph):
    (snapshot,) = evidence_ids(estate_graph, E.CONTRACT, EvidenceKind.CONFIG_SNAPSHOT)
    (record,) = evidence_ids(estate_graph, E.CONTRACT, EvidenceKind.DOCUMENT_REF)
    impact = stale_by_change(estate_graph, E.CHG_CONTRACT)
    assert [s.evidence_id for s in impact.evidence] == [snapshot]
    assert record not in [s.evidence_id for s in impact.evidence]  # ABOUT, not COLLECTED_FROM
    assert impact.assessment_ids == (E.ca(E.VC_EGRESS, E.CONTRACT),)
    # The missing DPA is a different assessment, so the change neither touches nor hides it.
    assert E.ca(E.VC_SUPPLIER_DPA, E.OPENAI) not in impact.assessment_ids


def test_a_change_with_nothing_collected_stales_nothing(estate_graph):
    graph = estate_graph.copy()
    (snapshot,) = evidence_ids(graph, E.CONTRACT, EvidenceKind.CONFIG_SNAPSHOT)
    graph.remove_edge(snapshot, E.RES_CONTRACT, (EdgeType.COLLECTED_FROM, None))
    impact = stale_by_change(graph, E.CHG_CONTRACT)
    assert impact.evidence == () and impact.assessment_ids == ()


def test_a_change_never_stales_another_systems_evidence_or_a_provider_document(estate_graph):
    (dpa,) = evidence_ids(estate_graph, E.BEDROCK, EvidenceKind.DOCUMENT_REF)
    touched = {
        s.evidence_id
        for c in (E.CHG_SUPPORT, E.CHG_TALENT, E.CHG_CONTRACT)
        for s in stale_by_change(estate_graph, c).evidence
    }
    assert dpa not in touched  # ABOUT a provider and never COLLECTED_FROM a resource
    support = {s.evidence_id for s in stale_by_change(estate_graph, E.CHG_SUPPORT).evidence}
    talent = {s.evidence_id for s in stale_by_change(estate_graph, E.CHG_TALENT).evidence}
    assert not support & talent


def test_stale_evidence_with_no_assessment_is_still_listed(estate_graph):
    graph = estate_graph.copy()
    for src, dst, key in list(graph.out_edges(keys=True)):
        if key[0] is EdgeType.SUPPORTS and dst == E.ca(E.VC_DISCLOSURE, E.SUPPORT):
            graph.remove_edge(src, dst, key)
    impact = stale_by_change(graph, E.CHG_SUPPORT)
    assert len(impact.evidence) == 1 and impact.evidence[0].assessment_ids == ()
    assert impact.assessment_ids == ()


def test_stale_needs_a_change_event(estate_graph):
    for bad in (E.RES_SUPPORT, "chg:nope"):
        with pytest.raises(ValueError, match="ChangeEvent"):
            stale_by_change(estate_graph, bad)


# --- The M1 matrix: all five traversals, for each of the three use cases -------------------

USE_CASES = {
    # system, its provider (None: in-house), a requirement to crosswalk, its change, a trail
    "support-assistant": (E.SUPPORT, E.BEDROCK, E.ART50_1, E.ISO, E.CHG_SUPPORT, E.ART50_1),
    "talent-screening": (E.TALENT, None, E.ART9_2A, E.ISO, E.CHG_TALENT, E.ART14),
    "contract-insights": (E.CONTRACT, E.OPENAI, E.ISO_A10_3, E.EUAIA, E.CHG_CONTRACT, E.ISO_A10_3),
}
CROSSWALK_LINKS = {"support-assistant": 1, "talent-screening": 1, "contract-insights": 0}
STALE_EVIDENCE = {"support-assistant": 1, "talent-screening": 1, "contract-insights": 1}


@pytest.mark.parametrize("name", USE_CASES)
def test_all_five_traversals_for_each_use_case(estate_graph, name):
    system, provider, requirement, framework, change, trail_requirement = USE_CASES[name]

    assert obligations_for(estate_graph, system)  # 1: what applies, and what proves it
    if provider is not None:  # 2: impact of the provider incident
        assert system in system_ids(provider_impact(estate_graph, provider))
    else:
        assert all(
            system not in system_ids(provider_impact(estate_graph, p))
            for p in (E.BEDROCK, E.OPENAI)
        )
    assert len(crosswalk(estate_graph, requirement, framework)) == CROSSWALK_LINKS[name]  # 3
    assert len(stale_by_change(estate_graph, change).evidence) == STALE_EVIDENCE[name]  # 4
    assert audit_trail(estate_graph, trail_requirement, system).links  # 5: audit trail
