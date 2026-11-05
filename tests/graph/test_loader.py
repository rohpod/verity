from datetime import datetime, timedelta
from uuid import uuid4

import networkx as nx
import pytest
from conftest import START
from factories import COMMON, make_edge, one_of_each
from verity_core.graph.loader import build_graph, in_edges, node_record, out_edges
from verity_core.graph.repository import GraphRepository
from verity_core.model.enums import EdgeType, NodeType, Role, Source
from verity_core.model.usage import UsageRecord

NODES = one_of_each()
PERSON, SYSTEM = NODES[NodeType.PERSON], NODES[NodeType.AI_SYSTEM]
REQ = NODES[NodeType.REQUIREMENT]


def owns():
    return make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id)


def days(n):
    return START + timedelta(days=n)


def test_nodes_and_edges_carry_their_records():
    edge = owns()
    graph = build_graph([PERSON, SYSTEM], [edge])
    assert isinstance(graph, nx.MultiDiGraph)
    assert graph.nodes[PERSON.id]["record"] == PERSON
    assert graph.get_edge_data(PERSON.id, SYSTEM.id, key=(EdgeType.OWNS, None))["record"] == edge


def test_two_roles_between_the_same_pair_are_two_edges():
    edges = [
        make_edge(EdgeType.APPLIES_TO, REQ.id, SYSTEM.id, role=role)
        for role in (Role.PROVIDER, Role.DEPLOYER)
    ]
    graph = build_graph([REQ, SYSTEM], edges)
    assert graph.number_of_edges(REQ.id, SYSTEM.id) == 2
    assert [e.qualifier for e in out_edges(graph, REQ.id)] == ["deployer", "provider"]


def test_closed_edges_and_nodes_are_left_out_by_default():
    closed = make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id, valid_from=days(-9), valid_to=days(-1))
    graph = build_graph([PERSON, SYSTEM], [closed])
    assert set(graph.nodes) == {PERSON.id, SYSTEM.id} and graph.number_of_edges() == 0

    gone = SYSTEM.model_copy(update={"valid_from": days(-9), "valid_to": days(-1)})
    assert SYSTEM.id not in build_graph([PERSON, gone], [])


def test_as_of_brings_back_what_existed_then():
    edge = make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id, valid_from=days(-9), valid_to=days(-1))
    assert build_graph([PERSON, SYSTEM], [edge], as_of=days(-5)).number_of_edges() == 1
    assert (
        build_graph([PERSON, SYSTEM], [edge], as_of=days(-1)).number_of_edges() == 0
    )  # [from, to)


def test_a_node_outside_its_validity_takes_its_edges_with_it():
    later = SYSTEM.model_copy(update={"valid_from": days(3)})
    edge = make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id, valid_from=days(-9))
    graph = build_graph([PERSON, later], [edge], as_of=days(0))
    assert SYSTEM.id not in graph and graph.number_of_edges() == 0
    assert SYSTEM.id in build_graph([PERSON, later], [edge], as_of=days(4))


def test_edges_to_missing_nodes_are_skipped():
    assert build_graph([PERSON], [owns()]).number_of_edges() == 0


def test_output_does_not_depend_on_input_order():
    nodes, edges = [SYSTEM, PERSON], [owns()]
    assert list(build_graph(nodes, edges).nodes) == list(build_graph(nodes[::-1], edges).nodes)


def test_hop_helpers_are_ordered_and_tolerate_missing_nodes():
    risk = NODES[NodeType.RISK]
    graph = build_graph(
        [PERSON, SYSTEM, risk],
        [make_edge(EdgeType.OWNS, PERSON.id, risk.id), owns()],
    )
    assert [e.dst for e in out_edges(graph, PERSON.id)] == [risk.id, SYSTEM.id]
    assert [e.dst for e in out_edges(graph, PERSON.id, EdgeType.OWNS)] == [risk.id, SYSTEM.id]
    assert out_edges(graph, PERSON.id, EdgeType.HAS_RISK) == []
    assert [e.src for e in in_edges(graph, SYSTEM.id)] == [PERSON.id]
    assert out_edges(graph, "sys:nope") == [] and in_edges(graph, "sys:nope") == []
    assert node_record(graph, PERSON.id) == PERSON and node_record(graph, "sys:nope") is None


# --- the repository's load_graph ---------------------------------------------------------


def test_load_graph_is_in_the_protocol(repo):
    assert isinstance(repo, GraphRepository)


def test_load_graph_returns_the_stored_graph(repo, clock):
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    repo.upsert_edge(owns())
    graph = repo.load_graph()
    assert set(graph.nodes) == {PERSON.id, SYSTEM.id}
    assert graph.nodes[SYSTEM.id]["record"] == repo.get_node(SYSTEM.id)
    assert len(out_edges(graph, PERSON.id)) == 1


def test_load_graph_follows_close_and_reopen(repo, clock):
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    repo.upsert_edge(owns())
    clock.advance(days=2)
    repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=clock.now)
    assert repo.load_graph().number_of_edges() == 0
    assert repo.load_graph(as_of=START + timedelta(days=1)).number_of_edges() == 1
    clock.advance(days=3)
    repo.upsert_edge(owns())
    assert repo.load_graph().number_of_edges() == 1
    assert repo.load_graph(as_of=START + timedelta(days=3)).number_of_edges() == 0  # the gap
    assert repo.load_graph(as_of=START + timedelta(days=1)).number_of_edges() == 1


def test_load_graph_leaves_out_usage_records(repo):
    repo.append_usage(
        UsageRecord(
            tenant=COMMON["tenant"],
            usage_id=uuid4(),
            system_id=SYSTEM.id,
            provider_id="prov:mock-bedrock",
            model_id="model:fm-1",
            timestamp=START,
            token_estimate=10,
            source=Source.SIMULATED,
        )
    )
    assert repo.load_graph().number_of_nodes() == 0


def test_a_naive_as_of_is_rejected_even_for_an_empty_graph(repo):
    with pytest.raises(ValueError, match="timezone-aware"):
        repo.load_graph(as_of=datetime(2026, 11, 5))
