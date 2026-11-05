"""Behaviour every GraphRepository must have. Uses only the protocol, via the `repo` fixture."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import START
from factories import COMMON, evidence, make_edge, one_of_each
from verity_core.graph.errors import (
    EdgeClosedError,
    ImmutableNodeError,
    InvalidEdgeError,
    InvalidNodeError,
    TenantMismatchError,
)
from verity_core.graph.repository import GraphRepository
from verity_core.model import ids
from verity_core.model.enums import (
    Direction,
    EdgeType,
    ModelOrigin,
    NodeType,
    RationaleType,
    Role,
)
from verity_core.model.nodes import Model, Organisation

NODES = one_of_each()
PERSON = NODES[NodeType.PERSON]
SYSTEM = NODES[NodeType.AI_SYSTEM]
RISK = NODES[NodeType.RISK]


def test_repository_satisfies_the_protocol(repo):
    assert isinstance(repo, GraphRepository)


# --- nodes ------------------------------------------------------------------------------


def test_get_node_returns_none_when_missing(repo):
    assert repo.get_node("sys:nope") is None


def test_new_node_is_stamped_by_the_repository(repo, clock):
    stored = repo.upsert_node(SYSTEM)
    assert stored.version == 1
    assert stored.created_at == stored.updated_at == clock.now
    assert stored.valid_from == clock.now
    assert repo.get_node(SYSTEM.id) == stored
    assert repo.history(SYSTEM.id) == [stored]


def test_a_supplied_valid_from_is_kept(repo):
    earlier = START - timedelta(days=30)
    assert repo.upsert_node(SYSTEM.model_copy(update={"valid_from": earlier})).valid_from == earlier


def test_unchanged_upsert_writes_nothing(repo, clock):
    first = repo.upsert_node(SYSTEM)
    clock.advance(days=1)
    again = repo.upsert_node(SYSTEM)  # valid_from unset, as a crawler would send it
    assert again == first
    assert again.version == 1 and again.updated_at == first.updated_at
    assert len(repo.history(SYSTEM.id)) == 1


def test_a_real_change_bumps_the_version_and_adds_history(repo, clock):
    first = repo.upsert_node(SYSTEM)
    clock.advance(days=1)
    second = repo.upsert_node(SYSTEM.model_copy(update={"purpose": "Rank candidates"}))
    assert second.version == 2
    assert second.created_at == first.created_at
    assert second.updated_at == clock.now
    assert second.valid_from == first.valid_from
    assert repo.history(SYSTEM.id) == [first, second]  # oldest first, current last
    assert repo.get_node(SYSTEM.id) == second


def test_history_of_an_unknown_node_is_empty(repo):
    assert repo.history("sys:nope") == []


def test_a_node_from_another_tenant_is_refused(repo):
    with pytest.raises(TenantMismatchError):
        repo.upsert_node(SYSTEM.model_copy(update={"tenant": "other"}))
    assert repo.get_node(SYSTEM.id) is None


def test_the_clock_must_be_timezone_aware(repo, clock):
    clock.now = datetime(2026, 11, 5)
    with pytest.raises(ValueError, match="timezone-aware"):
        repo.upsert_node(SYSTEM)


def test_nodes_by_type_is_filtered_and_ordered(repo):
    for slug in ("b", "a", "c"):
        repo.upsert_node(SYSTEM.model_copy(update={"id": ids.system_id(slug)}))
    repo.upsert_node(PERSON)
    assert [n.id for n in repo.nodes_by_type(NodeType.AI_SYSTEM)] == [
        "sys:a",
        "sys:b",
        "sys:c",
    ]
    assert repo.nodes_by_type(NodeType.PROVIDER) == []


def test_evidence_is_immutable(repo, clock):
    e = repo.upsert_node(evidence())
    clock.advance(days=1)
    assert repo.upsert_node(evidence()) == e  # identical: no-op
    with pytest.raises(ImmutableNodeError):
        repo.upsert_node(evidence().model_copy(update={"confidence": 0.5}))
    assert repo.history(e.id) == [e]


def test_recollecting_evidence_creates_a_new_node(repo, clock):
    first = repo.upsert_node(evidence())
    later = evidence(
        collected_at=clock.now + timedelta(days=1), valid_until=clock.now + timedelta(days=30)
    )
    second = repo.upsert_node(later)
    assert second.id != first.id and second.sha256 == first.sha256
    assert len(repo.nodes_by_type(NodeType.EVIDENCE)) == 2


def test_a_tenant_has_one_organisation(repo):
    org = repo.upsert_node(NODES[NodeType.ORGANISATION])
    assert repo.upsert_node(org.model_copy(update={"name": "Renamed"})).version == 2
    with pytest.raises(InvalidNodeError) as caught:
        repo.upsert_node(Organisation(id=ids.organisation_id("other"), name="Other", **COMMON))
    assert caught.value.rule == "organisation_per_tenant"
    assert len(repo.nodes_by_type(NodeType.ORGANISATION)) == 1


# --- edges ------------------------------------------------------------------------------


def owns(repo):
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    return make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id)


def test_edges_need_both_nodes_first(repo):
    edge = make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id)
    with pytest.raises(InvalidEdgeError) as caught:
        repo.upsert_edge(edge)
    assert caught.value.rule == "missing_endpoint"
    repo.upsert_node(PERSON)
    with pytest.raises(InvalidEdgeError):
        repo.upsert_edge(edge)
    assert repo.neighbors(PERSON.id, Direction.OUT) == []


def test_new_edge_is_stamped(repo, clock):
    stored = repo.upsert_edge(owns(repo))
    assert stored.version == 1
    assert stored.created_at == stored.updated_at == stored.valid_from == clock.now


def test_unchanged_edge_upsert_writes_nothing(repo, clock):
    first = repo.upsert_edge(owns(repo))
    clock.advance(days=1)
    again = repo.upsert_edge(owns(repo))
    assert again == first and again.version == 1


def test_changed_edge_properties_bump_the_version(repo, clock):
    repo.upsert_node(NODES[NodeType.REQUIREMENT])
    repo.upsert_node(NODES[NodeType.CONTROL])
    mapping = make_edge(EdgeType.MAPS_TO, "req:euaia:art50-1", "ctl:VC-014")
    first = repo.upsert_edge(mapping)
    clock.advance(days=1)
    second = repo.upsert_edge(
        make_edge(
            EdgeType.MAPS_TO,
            "req:euaia:art50-1",
            "ctl:VC-014",
            rationale="Revised rationale.",
            rationale_type=RationaleType.SEMANTIC,
        )
    )
    assert second.version == 2 and second.created_at == first.created_at
    assert len(repo.neighbors("req:euaia:art50-1", Direction.OUT, EdgeType.MAPS_TO)) == 1


def test_one_applies_to_edge_per_role(repo):
    repo.upsert_node(NODES[NodeType.REQUIREMENT])
    repo.upsert_node(SYSTEM)
    for role in (Role.PROVIDER, Role.DEPLOYER):
        repo.upsert_edge(make_edge(EdgeType.APPLIES_TO, "req:euaia:art50-1", SYSTEM.id, role=role))
    found = repo.neighbors(SYSTEM.id, Direction.IN, EdgeType.APPLIES_TO)
    assert [e.qualifier for e in found] == ["deployer", "provider"]


def test_edge_from_another_tenant_is_refused(repo):
    edge = owns(repo)
    with pytest.raises(TenantMismatchError):
        repo.upsert_edge(edge.model_copy(update={"tenant": "other"}))


def test_provided_by_on_an_in_house_model_is_rejected(repo):
    in_house = NODES[NodeType.MODEL]
    provider = NODES[NodeType.PROVIDER]
    repo.upsert_node(in_house)
    repo.upsert_node(provider)
    with pytest.raises(InvalidEdgeError) as caught:
        repo.upsert_edge(make_edge(EdgeType.PROVIDED_BY, in_house.id, provider.id))
    assert caught.value.rule == "provided_by_third_party_only"
    assert repo.neighbors(in_house.id, Direction.OUT) == []


def test_a_provided_model_cannot_be_flipped_to_in_house(repo):
    third_party: Model = NODES[NodeType.MODEL].model_copy(
        update={"origin": ModelOrigin.THIRD_PARTY}
    )
    provider = NODES[NodeType.PROVIDER]
    repo.upsert_node(third_party)
    repo.upsert_node(provider)
    repo.upsert_edge(make_edge(EdgeType.PROVIDED_BY, third_party.id, provider.id))
    with pytest.raises(InvalidEdgeError):
        repo.upsert_node(third_party.model_copy(update={"origin": ModelOrigin.IN_HOUSE}))
    assert repo.get_node(third_party.id).origin is ModelOrigin.THIRD_PARTY
    assert len(repo.history(third_party.id)) == 1


def test_a_control_assessment_cannot_have_two_scopes(repo):
    ca = NODES[NodeType.CONTROL_ASSESSMENT]
    for node in (ca, SYSTEM, NODES[NodeType.ORGANISATION]):
        repo.upsert_node(node)
    repo.upsert_edge(make_edge(EdgeType.SCOPED_TO, ca.id, SYSTEM.id))
    with pytest.raises(InvalidEdgeError) as caught:
        repo.upsert_edge(make_edge(EdgeType.SCOPED_TO, ca.id, NODES[NodeType.ORGANISATION].id))
    assert caught.value.rule == "max_out"
    repo.upsert_edge(make_edge(EdgeType.SCOPED_TO, ca.id, SYSTEM.id))  # same edge again is fine


def test_neighbors_by_direction_and_type(repo):
    owns_edge = repo.upsert_edge(owns(repo))
    repo.upsert_node(RISK)
    has_risk = repo.upsert_edge(make_edge(EdgeType.HAS_RISK, SYSTEM.id, RISK.id))
    repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, RISK.id))
    assert repo.neighbors(SYSTEM.id, Direction.IN) == [owns_edge]
    assert repo.neighbors(SYSTEM.id, Direction.OUT) == [has_risk]
    assert repo.neighbors(SYSTEM.id, Direction.OUT, EdgeType.OWNS) == []
    assert [e.dst for e in repo.neighbors(PERSON.id, Direction.OUT)] == [RISK.id, SYSTEM.id]
    assert repo.neighbors("sys:nope", Direction.OUT) == []


def test_neighbors_respect_validity_at_as_of(repo):
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    start, end = START - timedelta(days=10), START - timedelta(days=2)
    past = repo.upsert_edge(
        make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id, valid_from=start, valid_to=end)
    )
    assert repo.neighbors(PERSON.id, Direction.OUT) == []  # closed, so not "currently open"
    middle = START - timedelta(days=5)
    assert repo.neighbors(PERSON.id, Direction.OUT, as_of=middle) == [past]
    assert repo.neighbors(PERSON.id, Direction.OUT, as_of=start) == [past]  # [from, to)
    assert repo.neighbors(PERSON.id, Direction.OUT, as_of=end) == []


def test_a_closed_edge_cannot_be_overwritten_yet(repo):
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    closed = make_edge(
        EdgeType.OWNS,
        PERSON.id,
        SYSTEM.id,
        valid_from=START - timedelta(days=3),
        valid_to=START - timedelta(days=1),
    )
    repo.upsert_edge(closed)
    with pytest.raises(EdgeClosedError):
        repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id))


def test_naive_as_of_is_rejected(repo):
    edge = repo.upsert_edge(owns(repo))
    with pytest.raises(ValueError, match="timezone-aware"):
        repo.neighbors(edge.src, Direction.OUT, as_of=datetime(2026, 11, 5))


def test_rejected_writes_leave_no_trace(repo):
    repo.upsert_node(NODES[NodeType.MODEL])
    with pytest.raises(InvalidEdgeError):
        repo.upsert_edge(make_edge(EdgeType.PROVIDED_BY, NODES[NodeType.MODEL].id, "prov:nope"))
    assert repo.neighbors(NODES[NodeType.MODEL].id, Direction.OUT) == []
    assert repo.neighbors("prov:nope", Direction.IN) == []
    assert UTC
