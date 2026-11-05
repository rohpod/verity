"""What `DynamoDBRepository` does to the table for edges (ADR 0013): the `E#` item and its
`R#` mirror move together, and ending a node closes its edges in chunks."""

from datetime import timedelta

import pytest
from conftest import START
from dynamo_support import SpyClient, aws_failure, repo_for, rows
from factories import make_edge, one_of_each
from verity_core.graph.dynamodb import items, keys
from verity_core.graph.dynamodb.table import TABLE_NAME
from verity_core.graph.errors import ConcurrentWriteError, EdgeNotFoundError
from verity_core.model import ids
from verity_core.model.enums import Direction, EdgeType, NodeType, Role

NODES = one_of_each()
PERSON, SYSTEM, RISK = (NODES[t] for t in (NodeType.PERSON, NodeType.AI_SYSTEM, NodeType.RISK))
CA, ORG = NODES[NodeType.CONTROL_ASSESSMENT], NODES[NodeType.ORGANISATION]
REQUIREMENT = NODES[NodeType.REQUIREMENT]


def seeded(table, *nodes, client=None):
    repo = repo_for(table, client=client)
    for node in nodes:
        repo.upsert_node(node)
    return repo


def item_at(table, pk_id, sk):
    found = table.client.get_item(
        TableName=TABLE_NAME,
        Key={"PK": {"S": keys.node_pk("kestrel", pk_id)}, "SK": {"S": sk}},
        ConsistentRead=True,
    )
    return found.get("Item")


def pair(table, edge):
    """The stored `E#` item and `R#` mirror of an edge."""
    return (
        item_at(table, edge.src, keys.edge_sk(edge.key)),
        item_at(table, edge.dst, keys.reverse_sk(edge.key)),
    )


def owns():
    return make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id)


# --- the item and its mirror ---------------------------------------------------------------


def test_an_edge_is_an_outgoing_item_and_a_reverse_mirror_with_one_document(table):
    repo = seeded(table, PERSON, SYSTEM)
    before = len(rows(table))
    stored = repo.upsert_edge(owns())
    forward, reverse = pair(table, stored)
    assert len(rows(table)) == before + 2
    assert forward["doc"] == reverse["doc"] and forward["ver"] == reverse["ver"] == {"N": "1"}
    assert items.edge_from_item(forward) == stored
    assert forward["PK"]["S"].endswith(PERSON.id) and reverse["PK"]["S"].endswith(SYSTEM.id)


def test_a_new_edge_is_one_batched_read_and_one_transaction(table):
    spy = SpyClient(table.client)
    repo = seeded(table, PERSON, SYSTEM, client=spy)
    spy.calls.clear()
    repo.upsert_edge(owns())
    assert dict(spy.calls) == {"batch_get_item": 1, "transact_write_items": 1}


def test_only_edge_types_that_limit_a_source_read_its_other_edges(table):
    spy = SpyClient(table.client)
    repo = seeded(table, CA, SYSTEM, NODES[NodeType.CONTROL], client=spy)
    spy.calls.clear()
    repo.upsert_edge(make_edge(EdgeType.SCOPED_TO, CA.id, SYSTEM.id))  # at most one per source
    assert spy.calls["query"] == 1 and spy.calls["batch_get_item"] == 1


def test_resending_an_unchanged_edge_writes_nothing(table):
    spy = SpyClient(table.client)
    repo = seeded(table, PERSON, SYSTEM, client=spy)
    repo.upsert_edge(owns())
    items_before = table.client.scan(TableName=TABLE_NAME)["Items"]
    writes = spy.calls["transact_write_items"]
    table.clock.advance(days=1)
    repo.upsert_edge(owns())
    assert table.client.scan(TableName=TABLE_NAME)["Items"] == items_before
    assert spy.calls["transact_write_items"] == writes


def test_changing_an_edge_updates_both_items_together(table):
    repo = seeded(table, REQUIREMENT, NODES[NodeType.CONTROL])
    first = make_edge(EdgeType.MAPS_TO, REQUIREMENT.id, "ctl:VC-014")
    repo.upsert_edge(first)
    table.clock.advance(days=1)
    changed = repo.upsert_edge(
        make_edge(EdgeType.MAPS_TO, REQUIREMENT.id, "ctl:VC-014", rationale="Revised.")
    )
    forward, reverse = pair(table, changed)
    assert changed.version == 2 and forward["ver"] == reverse["ver"] == {"N": "2"}
    assert forward["doc"] == reverse["doc"]


def test_two_roles_are_two_items_each_way_and_closing_one_leaves_the_other(table):
    repo = seeded(table, REQUIREMENT, SYSTEM)
    for role in (Role.PROVIDER, Role.DEPLOYER):
        repo.upsert_edge(make_edge(EdgeType.APPLIES_TO, REQUIREMENT.id, SYSTEM.id, role=role))
    applies = [sk for _, sk in rows(table) if "APPLIES_TO" in sk]
    assert sorted(applies) == [
        f"E#APPLIES_TO#{SYSTEM.id}#deployer",
        f"E#APPLIES_TO#{SYSTEM.id}#provider",
        f"R#APPLIES_TO#{REQUIREMENT.id}#deployer",
        f"R#APPLIES_TO#{REQUIREMENT.id}#provider",
    ]
    table.clock.advance(days=1)
    repo.close_edge(
        REQUIREMENT.id,
        EdgeType.APPLIES_TO,
        SYSTEM.id,
        valid_to=table.clock.now,
        qualifier="provider",
    )
    still_open = repo.neighbors(SYSTEM.id, Direction.IN)
    assert [e.qualifier for e in still_open] == ["deployer"]


# --- both items or neither -----------------------------------------------------------------


def test_a_failed_condition_on_the_mirror_leaves_the_forward_item_untouched(table):
    repo = seeded(table, REQUIREMENT, NODES[NodeType.CONTROL])
    edge = repo.upsert_edge(make_edge(EdgeType.MAPS_TO, REQUIREMENT.id, "ctl:VC-014"))
    forward_before, _ = pair(table, edge)
    # Make the mirror look like another writer already changed it.
    table.client.update_item(
        TableName=TABLE_NAME,
        Key={
            "PK": {"S": keys.node_pk("kestrel", edge.dst)},
            "SK": {"S": keys.reverse_sk(edge.key)},
        },
        UpdateExpression="SET ver = :v",
        ExpressionAttributeValues={":v": {"N": "99"}},
    )
    with pytest.raises(ConcurrentWriteError):
        repo.upsert_edge(
            make_edge(EdgeType.MAPS_TO, REQUIREMENT.id, "ctl:VC-014", rationale="Revised.")
        )
    assert pair(table, edge)[0] == forward_before  # the forward item was not changed either


def test_a_competing_edge_write_between_the_read_and_the_write_is_caught(table):
    spy = SpyClient(table.client)
    a = seeded(table, REQUIREMENT, NODES[NodeType.CONTROL], client=spy)
    b = repo_for(table)
    edge = a.upsert_edge(make_edge(EdgeType.MAPS_TO, REQUIREMENT.id, "ctl:VC-014"))
    spy.before["transact_write_items"] = lambda: b.upsert_edge(
        make_edge(EdgeType.MAPS_TO, REQUIREMENT.id, "ctl:VC-014", rationale="B first")
    )
    with pytest.raises(ConcurrentWriteError):
        a.upsert_edge(make_edge(EdgeType.MAPS_TO, REQUIREMENT.id, "ctl:VC-014", rationale="A"))
    forward, reverse = pair(table, edge)
    assert forward["doc"] == reverse["doc"] and items.edge_from_item(forward).rationale == "B first"


def test_two_writers_creating_one_edge_leave_a_consistent_pair(table):
    spy = SpyClient(table.client)
    a = seeded(table, PERSON, SYSTEM, client=spy)
    b = repo_for(table)
    spy.before["transact_write_items"] = lambda: b.upsert_edge(owns())
    with pytest.raises(ConcurrentWriteError):
        a.upsert_edge(owns())
    forward, reverse = pair(table, owns())
    assert forward["doc"] == reverse["doc"]


# --- closing and reopening -----------------------------------------------------------------


def test_closing_changes_both_items_and_closing_again_writes_nothing(table):
    spy = SpyClient(table.client)
    repo = seeded(table, PERSON, SYSTEM, client=spy)
    repo.upsert_edge(owns())
    table.clock.advance(days=2)
    closed = repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=table.clock.now)
    forward, reverse = pair(table, closed)
    assert closed.valid_to == table.clock.now and closed.version == 2
    assert forward["doc"] == reverse["doc"] and forward["ver"] == reverse["ver"] == {"N": "2"}
    writes = spy.calls["transact_write_items"]
    table.clock.advance(days=3)
    again = repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=table.clock.now)
    assert again == closed and spy.calls["transact_write_items"] == writes


def test_closing_an_unknown_edge_raises(table):
    repo = seeded(table, PERSON, SYSTEM)
    with pytest.raises(EdgeNotFoundError):
        repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=START)
    with pytest.raises(ValueError, match="timezone-aware"):
        repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=START.replace(tzinfo=None))


def test_reopening_keeps_the_earlier_period_in_both_items(table):
    repo = seeded(table, PERSON, SYSTEM)
    first = repo.upsert_edge(owns())
    table.clock.advance(days=2)
    closed_at = table.clock.now
    repo.close_edge(PERSON.id, EdgeType.OWNS, SYSTEM.id, valid_to=closed_at)
    table.clock.advance(days=3)
    reopened = repo.upsert_edge(owns())
    forward, reverse = pair(table, reopened)
    assert reopened.closed_intervals == ((first.valid_from, closed_at),)
    assert forward["doc"] == reverse["doc"] and forward["ver"] == {"N": "3"}
    assert repo.neighbors(SYSTEM.id, Direction.IN) == [reopened]


# --- ending a node closes its edges --------------------------------------------------------


def end(node, table):
    return node.model_copy(update={"valid_from": START, "valid_to": table.clock.now})


def many_systems(table, count):
    repo = seeded(table, PERSON)
    for n in range(count):
        system = SYSTEM.model_copy(update={"id": ids.system_id(f"s{n:03d}")})
        repo.upsert_node(system)
        repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, system.id))
    return repo


def test_ending_a_node_closes_its_incoming_and_outgoing_edges(table):
    repo = seeded(table, PERSON, SYSTEM, RISK)
    repo.upsert_edge(owns())
    repo.upsert_edge(make_edge(EdgeType.HAS_RISK, SYSTEM.id, RISK.id))
    table.clock.advance(days=2)
    repo.upsert_node(end(SYSTEM, table))
    for edge in (owns(), make_edge(EdgeType.HAS_RISK, SYSTEM.id, RISK.id)):
        forward, reverse = pair(table, edge)
        assert forward["doc"] == reverse["doc"]
        assert items.edge_from_item(forward).valid_to == table.clock.now
    assert repo.neighbors(SYSTEM.id, Direction.IN) == [] == repo.neighbors(SYSTEM.id, Direction.OUT)


def test_a_node_with_many_edges_is_closed_fifty_edges_to_a_transaction(table):
    spy = SpyClient(table.client)
    many_systems(table, 120)
    repo = repo_for(table, client=spy)
    table.clock.advance(days=2)
    repo.upsert_node(end(PERSON, table))
    # 120 edges is 3 transactions of 50, 50 and 20 edges (100, 100 and 40 items), then the node.
    assert spy.calls["transact_write_items"] == 4
    assert repo.neighbors(PERSON.id, Direction.OUT) == []
    for n in (0, 59, 119):
        edge = make_edge(EdgeType.OWNS, PERSON.id, ids.system_id(f"s{n:03d}"))
        forward, reverse = pair(table, edge)
        assert forward["doc"] == reverse["doc"]
        assert items.edge_from_item(forward).valid_to == table.clock.now


def test_a_failed_run_can_be_repeated(table):
    spy = SpyClient(table.client)
    many_systems(table, 120)
    repo = repo_for(table, client=spy)
    table.clock.advance(days=2)
    ended = end(PERSON, table)
    spy.fail[("transact_write_items", 2)] = aws_failure()  # the second chunk of edges fails
    with pytest.raises(Exception, match="simulated"):
        repo.upsert_node(ended)
    # The edges close before the node, so it is not ended and the first chunk already is.
    assert repo.get_node(PERSON.id).valid_to is None
    assert len(repo.neighbors(PERSON.id, Direction.OUT)) == 70
    repo.upsert_node(ended)  # the same call, repeated
    assert repo.get_node(PERSON.id).valid_to == table.clock.now
    assert repo.neighbors(PERSON.id, Direction.OUT) == []
    assert [v.version for v in repo.history(PERSON.id)] == [1, 2]


def test_a_failed_node_write_after_the_edges_closed_is_also_repeatable(table):
    spy = SpyClient(table.client)
    repo = seeded(table, PERSON, SYSTEM, client=spy)
    repo.upsert_edge(owns())
    table.clock.advance(days=2)
    spy.fail[("transact_write_items", spy.calls["transact_write_items"] + 2)] = aws_failure()
    with pytest.raises(Exception, match="simulated"):
        repo.upsert_node(end(SYSTEM, table))  # call 1 closes the edge, call 2 writes the node
    assert repo.get_node(SYSTEM.id).valid_to is None
    assert repo.neighbors(SYSTEM.id, Direction.IN) == []
    repo.upsert_node(end(SYSTEM, table))
    assert repo.get_node(SYSTEM.id).valid_to == table.clock.now


# --- tenants -------------------------------------------------------------------------------


def test_the_same_edge_in_two_tenants_never_mixes(table):
    for tenant in ("kestrel", "other"):
        repo = repo_for(table, tenant)
        for node in (PERSON, SYSTEM):
            repo.upsert_node(node.model_copy(update={"tenant": tenant}))
        repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id, tenant=tenant))
    mine = repo_for(table, "kestrel").neighbors(PERSON.id, Direction.OUT)
    theirs = repo_for(table, "other").neighbors(PERSON.id, Direction.OUT)
    assert [e.tenant for e in mine] == ["kestrel"] and [e.tenant for e in theirs] == ["other"]


def test_an_edge_from_another_tenant_is_refused(table):
    from verity_core.graph.errors import TenantMismatchError

    repo = seeded(table, PERSON, SYSTEM)
    with pytest.raises(TenantMismatchError):
        repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id, tenant="other"))


def test_every_edge_closed_by_one_call_gets_the_same_timestamp(table):
    many_systems(table, 60)  # two chunks
    table.clock.advance(days=1)
    repo_for(table).upsert_node(end(PERSON, table))
    stamps = set()
    for n in range(60):
        edge = make_edge(EdgeType.OWNS, PERSON.id, ids.system_id(f"s{n:03d}"))
        stamps.add(items.edge_from_item(pair(table, edge)[0]).updated_at)
    assert stamps == {START + timedelta(days=1)}
