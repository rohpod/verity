"""Tier 3 rejection: problems visible only in the whole graph (ADR 0012)."""

import pytest
from factories import evidence, make_edge, one_of_each
from verity_core.graph.integrity import IntegrityIssue, check_integrity
from verity_core.graph.loader import build_graph
from verity_core.model import ids
from verity_core.model.enums import (
    AssuranceLevel,
    EdgeType,
    ModelOrigin,
    NodeType,
    ScopeLevel,
)

NODES = one_of_each()
SYSTEM = NODES[NodeType.AI_SYSTEM]
CONTROL = NODES[NodeType.CONTROL]
CA = NODES[NodeType.CONTROL_ASSESSMENT]
ORG = NODES[NodeType.ORGANISATION]
PROVIDER = NODES[NodeType.PROVIDER]
PERSON = NODES[NodeType.PERSON]
MODEL = NODES[NodeType.MODEL].model_copy(update={"origin": ModelOrigin.THIRD_PARTY})
EVIDENCE = evidence(subject=SYSTEM.id)
PARENT = NODES[NodeType.REQUIREMENT]
CHILD = PARENT.model_copy(update={"id": ids.requirement_id("euaia", "art50-2")})


def sound(*, nodes=(), drop=(), extra_edges=()):
    """A graph with no issues. `drop` removes named edges; `nodes` replaces nodes by ID."""
    base = [SYSTEM, CONTROL, CA, ORG, PROVIDER, PERSON, MODEL, EVIDENCE, PARENT, CHILD]
    replaced = {n.id: n for n in nodes}
    edges = {
        "provided_by": make_edge(EdgeType.PROVIDED_BY, MODEL.id, PROVIDER.id),
        "assesses": make_edge(EdgeType.ASSESSES, CA.id, CONTROL.id),
        "scoped_to": make_edge(EdgeType.SCOPED_TO, CA.id, SYSTEM.id),
        "about": make_edge(EdgeType.ABOUT, EVIDENCE.id, SYSTEM.id),
        "part_of": make_edge(EdgeType.PART_OF, CHILD.id, PARENT.id),
    }
    kept = [e for name, e in edges.items() if name not in drop]
    return build_graph([replaced.get(n.id, n) for n in base], [*kept, *extra_edges])


def codes(graph):
    return [issue.code for issue in check_integrity(graph)]


def test_a_sound_graph_has_no_issues():
    assert check_integrity(sound()) == []
    assert check_integrity(build_graph([], [])) == []


def test_third_party_model_without_a_provider():
    assert codes(sound(drop=["provided_by"])) == ["third_party_model_without_provider"]


def test_in_house_model_needs_no_provider():
    in_house = MODEL.model_copy(update={"origin": ModelOrigin.IN_HOUSE})
    assert check_integrity(sound(nodes=[in_house], drop=["provided_by"])) == []


def test_assessment_missing_its_control_or_scope():
    assert codes(sound(drop=["assesses"])) == ["assessment_without_control"]
    assert codes(sound(drop=["scoped_to"])) == ["assessment_without_scope"]
    assert set(codes(sound(drop=["assesses", "scoped_to"]))) == {
        "assessment_without_control",
        "assessment_without_scope",
    }


@pytest.mark.parametrize(
    "scope_level,scope,ok",
    [
        (ScopeLevel.SYSTEM, SYSTEM, True),
        (ScopeLevel.SYSTEM, ORG, False),
        (ScopeLevel.SYSTEM, PROVIDER, False),
        (ScopeLevel.ORGANISATION, ORG, True),
        (ScopeLevel.ORGANISATION, SYSTEM, False),
        (ScopeLevel.PROVIDER, PROVIDER, True),
        (ScopeLevel.PROVIDER, SYSTEM, False),
    ],
)
def test_the_scope_must_match_the_controls_scope_level(scope_level, scope, ok):
    control = CONTROL.model_copy(update={"scope_level": scope_level})
    rescoped = make_edge(EdgeType.SCOPED_TO, CA.id, scope.id)
    graph = sound(nodes=[control], drop=["scoped_to"], extra_edges=[rescoped])
    assert codes(graph) == ([] if ok else ["scope_level_mismatch"])


def test_l4_needs_an_assessed_edge_from_the_named_person():
    l4 = CA.model_copy(
        update={"assurance_level": AssuranceLevel.L4_VERIFIED, "assessor": PERSON.id}
    )
    assert codes(sound(nodes=[l4])) == ["l4_without_assessed_edge"]
    assessed = make_edge(EdgeType.ASSESSED, PERSON.id, CA.id)
    assert check_integrity(sound(nodes=[l4], extra_edges=[assessed])) == []
    other = ids.person_id("someone-else")
    wrong = make_edge(EdgeType.ASSESSED, other, CA.id)
    # The other person is not in the graph, so that edge is skipped and the issue stands.
    assert codes(sound(nodes=[l4], extra_edges=[wrong])) == ["l4_without_assessed_edge"]


def test_evidence_must_be_about_its_subject():
    assert codes(sound(drop=["about"])) == ["evidence_not_about_subject"]
    other = make_edge(EdgeType.ABOUT, EVIDENCE.id, ORG.id)
    assert codes(sound(drop=["about"], extra_edges=[other])) == ["evidence_not_about_subject"]


def test_requirement_cycles_are_found_once():
    back = make_edge(EdgeType.PART_OF, PARENT.id, CHILD.id)
    issues = check_integrity(sound(extra_edges=[back]))
    assert [i.code for i in issues] == ["part_of_cycle"]
    assert issues[0].node_id == min(PARENT.id, CHILD.id)
    assert CHILD.id in issues[0].message and PARENT.id in issues[0].message


def test_issues_are_ordered_and_describe_themselves():
    issues = check_integrity(sound(drop=["provided_by", "about", "assesses"]))
    assert issues == sorted(issues, key=lambda i: (i.node_id, i.code))
    assert all(isinstance(i, IntegrityIssue) and i.message for i in issues)
    assert len(issues) == 3
