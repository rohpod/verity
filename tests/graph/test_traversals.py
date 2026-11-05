"""The section E traversals as executable tests, for the three use cases.

Traversals 1 and 5 are here; PR 9 adds 2, 3 and 4. The estate (`estate.py`) is fictional and
its mappings are placeholders, so these tests check graph behaviour, not legal content.
"""

import estate as E
import pytest
from verity_core.graph.integrity import check_integrity
from verity_core.graph.loader import build_graph
from verity_core.graph.traversals import Resolution, audit_trail, obligations_for
from verity_core.model.enums import (
    AssuranceLevel,
    EvidenceKind,
    ImplementationStatus,
    Role,
    Source,
)

R = Resolution


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
    # but no evidence (a gap); human oversight is signed off; the in-house model has no provider.
    E.TALENT: [
        (E.ART14, Role.PROVIDER, E.VC_OVERSIGHT, R.DIRECT, None, E.ca(E.VC_OVERSIGHT, E.TALENT), 1),
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
    (evidence,) = link.evidence
    assert evidence.kind is EvidenceKind.ATTESTATION and evidence.collector == E.VERIFIER
    assert evidence.source is Source.SIMULATED


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
