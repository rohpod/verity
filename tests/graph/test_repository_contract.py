"""Behaviour every GraphRepository must have. Uses only the protocol, via the `repo` fixture."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import START, unwrap
from factories import COMMON, evidence, make_edge, one_of_each
from verity_core.graph.errors import (
    EdgeNotFoundError,
    ImmutableNodeError,
    InvalidEdgeError,
    InvalidNodeError,
    TenantMismatchError,
)
from verity_core.graph.repository import GraphRepository, UsageSink
from verity_core.model import ids
from verity_core.model.enums import (
    Direction,
    EdgeType,
    ModelOrigin,
    NodeType,
    RationaleType,
    Role,
    Source,
)
from verity_core.model.nodes import Model, Organisation
from verity_core.model.usage import UsageRecord

NODES = one_of_each()
PERSON = NODES[NodeType.PERSON]
SYSTEM = NODES[NodeType.AI_SYSTEM]
RISK = NODES[NodeType.RISK]


def test_repository_satisfies_the_protocol(repo):
    assert isinstance(unwrap(repo), GraphRepository)


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


# --- close_edge and reopening (D7) ---------------------------------------------------------


def test_close_edge_ends_the_edge_but_keeps_the_past(repo, clock):
    edge = repo.upsert_edge(owns(repo))
    clock.advance(days=2)
    closed = repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=clock.now)
    assert closed.valid_to == clock.now and closed.version == 2
    assert closed.created_at == edge.created_at and closed.updated_at == clock.now
    assert repo.neighbors(PERSON.id, Direction.OUT) == []
    assert repo.neighbors(PERSON.id, Direction.OUT, as_of=START + timedelta(days=1)) == [closed]
    assert repo.neighbors(PERSON.id, Direction.OUT, as_of=clock.now) == []  # [from, to)
    assert repo.neighbors(SYSTEM.id, Direction.IN) == []


def test_closing_a_closed_edge_keeps_the_first_valid_to(repo, clock):
    repo.upsert_edge(owns(repo))
    clock.advance(days=1)
    first = repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=clock.now)
    clock.advance(days=5)
    again = repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=clock.now)
    assert again == first and again.version == 2


def test_closing_an_unknown_edge_raises(repo):
    owns(repo)
    with pytest.raises(EdgeNotFoundError):
        repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=START)


def test_valid_to_cannot_precede_valid_from(repo):
    repo.upsert_edge(owns(repo))
    with pytest.raises(ValueError):
        repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=START - timedelta(days=1))
    assert len(repo.neighbors(PERSON.id, Direction.OUT)) == 1


def test_close_edge_needs_an_aware_valid_to(repo):
    repo.upsert_edge(owns(repo))
    with pytest.raises(ValueError, match="timezone-aware"):
        repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=datetime(2026, 11, 6))


def test_close_edge_with_a_qualifier_closes_one_role_only(repo, clock):
    repo.upsert_node(NODES[NodeType.REQUIREMENT])
    repo.upsert_node(SYSTEM)
    req = "req:euaia:art50-1"
    for role in (Role.PROVIDER, Role.DEPLOYER):
        repo.upsert_edge(make_edge(EdgeType.APPLIES_TO, req, SYSTEM.id, role=role))
    clock.advance(days=1)
    repo.close_edge(req, EdgeType.APPLIES_TO, SYSTEM.id, valid_to=clock.now, qualifier="provider")
    assert [e.qualifier for e in repo.neighbors(req, Direction.OUT)] == ["deployer"]
    with pytest.raises(EdgeNotFoundError):  # a qualified edge is not found without its qualifier
        repo.close_edge(req, EdgeType.APPLIES_TO, SYSTEM.id, valid_to=clock.now)


def test_closing_frees_a_max_out_slot(repo, clock):
    ca, org = NODES[NodeType.CONTROL_ASSESSMENT], NODES[NodeType.ORGANISATION]
    for node in (ca, SYSTEM, org):
        repo.upsert_node(node)
    repo.upsert_edge(make_edge(EdgeType.SCOPED_TO, ca.id, SYSTEM.id))
    clock.advance(days=1)
    repo.close_edge(ca.id, EdgeType.SCOPED_TO, SYSTEM.id, valid_to=clock.now)
    repo.upsert_edge(make_edge(EdgeType.SCOPED_TO, ca.id, org.id))  # no longer a second scope


def test_a_closed_edge_that_reappears_keeps_its_earlier_period(repo, clock):
    first = repo.upsert_edge(owns(repo))
    clock.advance(days=2)
    closed_at = clock.now
    repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=closed_at)
    clock.advance(days=3)
    reopened = repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id))

    assert reopened.valid_from == clock.now and reopened.valid_to is None
    assert reopened.closed_intervals == ((first.valid_from, closed_at),)
    assert reopened.version == 3 and reopened.created_at == first.created_at
    assert repo.neighbors(PERSON.id, Direction.OUT) == [reopened]

    def active(days):
        when = START + timedelta(days=days)
        return bool(repo.neighbors(PERSON.id, Direction.OUT, as_of=when))

    assert active(1)  # first period
    assert not active(3)  # gap
    assert active(5)  # second period


def test_an_edge_that_flaps_twice_keeps_both_earlier_periods(repo, clock):
    repo.upsert_edge(owns(repo))
    for _ in range(2):
        clock.advance(days=1)
        repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=clock.now)
        clock.advance(days=1)
        edge = repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id))
    assert len(edge.closed_intervals) == 2 and edge.version == 5
    assert len(repo.neighbors(PERSON.id, Direction.OUT)) == 1


def test_an_edge_cannot_reopen_before_it_closed(repo, clock):
    repo.upsert_edge(owns(repo))
    clock.advance(days=5)
    repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=clock.now)
    clock.advance(days=-1)  # a clock that went backwards
    with pytest.raises(ValueError, match="before it closed"):
        repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id))


def test_seeding_the_same_closed_edge_twice_changes_nothing(repo, clock):
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    historic = make_edge(
        EdgeType.OWNS,
        PERSON.id,
        SYSTEM.id,
        valid_from=START - timedelta(days=9),
        valid_to=START - timedelta(days=1),
    )
    first = repo.upsert_edge(historic)
    clock.advance(days=1)
    assert repo.upsert_edge(historic) == first
    assert first.version == 1 and first.closed_intervals == ()


def test_a_correction_to_a_closed_edge_keeps_it_closed(repo):
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    start = START - timedelta(days=9)
    repo.upsert_edge(
        make_edge(
            EdgeType.OWNS,
            PERSON.id,
            SYSTEM.id,
            valid_from=start,
            valid_to=start + timedelta(days=1),
        )
    )
    corrected = repo.upsert_edge(
        make_edge(
            EdgeType.OWNS,
            PERSON.id,
            SYSTEM.id,
            valid_from=start,
            valid_to=start + timedelta(days=2),
        )
    )
    assert corrected.valid_to == start + timedelta(days=2)
    assert corrected.version == 2 and corrected.closed_intervals == ()


def test_reseeding_an_edge_that_was_closed_reopens_it_without_overlap(repo, clock):
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    seeded = make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id, valid_from=START)
    repo.upsert_edge(seeded)
    clock.advance(days=2)
    closed_at = clock.now
    repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=closed_at)
    clock.advance(days=3)
    reopened = repo.upsert_edge(seeded)  # its valid_from predates the close, so it is stale
    assert reopened.valid_from == clock.now
    assert reopened.closed_intervals == ((START, closed_at),)
    clock.advance(days=1)
    assert repo.upsert_edge(seeded) == reopened  # seeding once more changes nothing


def test_a_closed_edge_cannot_be_given_a_future_end(repo, clock):
    repo.upsert_edge(owns(repo))
    with pytest.raises(ValueError, match="future"):
        repo.close_edge(
            PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=clock.now + timedelta(days=30)
        )
    assert len(repo.neighbors(PERSON.id, Direction.OUT)) == 1


def test_records_cannot_be_written_with_a_future_end(repo, clock):
    later = clock.now + timedelta(days=1)
    with pytest.raises(ValueError, match="future"):
        repo.upsert_node(SYSTEM.model_copy(update={"valid_from": clock.now, "valid_to": later}))
    edge = owns(repo)
    with pytest.raises(ValueError, match="future"):
        repo.upsert_edge(edge.model_copy(update={"valid_from": clock.now, "valid_to": later}))
    assert repo.neighbors(PERSON.id, Direction.OUT) == []


# --- what the repository hands back --------------------------------------------------------


def test_changing_a_returned_record_never_changes_what_is_stored(repo):
    stored = repo.upsert_node(evidence())
    original = dict(stored.content)
    stored.content["runtime"] = "tampered"  # through the upsert result
    repo.get_node(stored.id).content["runtime"] = "tampered"
    repo.history(stored.id)[0].content["runtime"] = "tampered"
    repo.nodes_by_type(NodeType.EVIDENCE)[0].content["runtime"] = "tampered"
    repo.load_graph().nodes[stored.id]["record"].content["runtime"] = "tampered"
    assert repo.get_node(stored.id).content == original
    assert repo.history(stored.id)[0].content == original


def test_changing_a_source_dict_after_writing_does_not_reach_the_store(repo):
    content = {"runtime": "python3.12"}
    e = evidence(content=content)
    repo.upsert_node(e)
    e.content["runtime"] = "tampered"
    assert repo.get_node(e.id).content == {"runtime": "python3.12"}


# --- ending a node -------------------------------------------------------------------------


def end(node, clock):
    return node.model_copy(update={"valid_from": START, "valid_to": clock.now})


def test_ending_a_node_closes_its_edges(repo, clock):
    repo.upsert_edge(owns(repo))
    repo.upsert_node(RISK)
    repo.upsert_edge(make_edge(EdgeType.HAS_RISK, SYSTEM.id, RISK.id))
    clock.advance(days=2)
    repo.upsert_node(end(SYSTEM, clock))
    assert repo.neighbors(PERSON.id, Direction.OUT) == []  # incoming edge closed
    assert repo.neighbors(RISK.id, Direction.IN) == []  # outgoing edge closed
    assert repo.load_graph().number_of_edges() == 0
    day_one = START + timedelta(days=1)
    assert len(repo.neighbors(PERSON.id, Direction.OUT, as_of=day_one)) == 1
    assert repo.load_graph(as_of=day_one).number_of_edges() == 2


def test_an_open_edge_to_an_ended_node_is_refused(repo, clock):
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    clock.advance(days=1)
    repo.upsert_node(end(SYSTEM, clock))
    with pytest.raises(InvalidEdgeError) as caught:
        repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id))
    assert caught.value.rule == "endpoint_ended"


def test_a_node_that_returns_can_take_edges_again(repo, clock):
    repo.upsert_edge(owns(repo))
    clock.advance(days=1)
    repo.upsert_node(end(SYSTEM, clock))
    clock.advance(days=1)
    repo.upsert_node(SYSTEM.model_copy(update={"valid_from": START}))  # rediscovered
    assert repo.neighbors(PERSON.id, Direction.OUT) == []  # edges come back only when re-sent
    edge = repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id))
    assert len(edge.closed_intervals) == 1


# --- usage (D7, D8) ------------------------------------------------------------------------


def usage(minutes=0, **overrides):
    fields = {
        "tenant": COMMON["tenant"],
        "usage_id": uuid4(),
        "system_id": SYSTEM.id,
        "provider_id": "prov:mock-bedrock",
        "model_id": "model:fm-1",
        "timestamp": START + timedelta(minutes=minutes),
        "token_estimate": 120,
        "source": Source.SIMULATED,
    } | overrides
    return UsageRecord(**fields)


def test_usage_can_be_written_with_only_the_narrow_sink(repo):
    assert isinstance(unwrap(repo), UsageSink)

    class OnlyAppends:
        def append_usage(self, record): ...

    assert isinstance(OnlyAppends(), UsageSink)
    assert not isinstance(OnlyAppends(), GraphRepository)


def test_usage_does_not_need_the_system_node(repo):
    assert repo.get_node(SYSTEM.id) is None
    record = usage()
    repo.append_usage(record)  # D8: the app role has no read access, so no existence check
    assert repo.usage_records(SYSTEM.id) == [record]


def test_usage_comes_back_oldest_first_and_per_system(repo):
    late, early, mid = usage(30), usage(0), usage(10)
    other = usage(5, system_id="sys:other")
    for record in (late, early, mid, other):
        repo.append_usage(record)
    assert repo.usage_records(SYSTEM.id) == [early, mid, late]
    assert repo.usage_records("sys:other") == [other]
    assert repo.usage_records("sys:none") == []


def test_usage_filter_is_half_open(repo):
    records = [usage(m) for m in (0, 10, 20)]
    for record in records:
        repo.append_usage(record)
    since, until = START + timedelta(minutes=10), START + timedelta(minutes=20)
    assert repo.usage_records(SYSTEM.id, since=since) == records[1:]
    assert repo.usage_records(SYSTEM.id, until=until) == records[:2]
    assert repo.usage_records(SYSTEM.id, since=since, until=until) == [records[1]]
    with pytest.raises(ValueError, match="timezone-aware"):
        repo.usage_records(SYSTEM.id, since=datetime(2026, 11, 5))


def test_a_retried_usage_write_is_stored_once(repo):
    record = usage()
    repo.append_usage(record)
    repo.append_usage(record)
    repo.append_usage(record.model_copy(update={"token_estimate": 999}))  # first write wins
    assert repo.usage_records(SYSTEM.id) == [record]


def test_two_calls_at_the_same_instant_are_both_kept(repo):
    first, second = usage(0), usage(0)
    repo.append_usage(first)
    repo.append_usage(second)
    assert len(repo.usage_records(SYSTEM.id)) == 2


def test_usage_from_another_tenant_is_refused(repo):
    with pytest.raises(TenantMismatchError):
        repo.append_usage(usage(tenant="other"))


def test_usage_never_appears_as_a_node_or_edge(repo):
    repo.append_usage(usage())
    assert all(repo.nodes_by_type(t) == [] for t in NodeType)
    assert repo.neighbors(SYSTEM.id, Direction.IN) == []
