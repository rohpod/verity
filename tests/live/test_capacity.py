"""Real consumed capacity against the estimates in `capacity.py`, which ADR 0014 relies on.
moto reports no capacity for transactions, so this is the first real measurement."""

from factories import evidence, make_edge
from live_support import PROBE_TENANT, live_only, probe_node, probe_session, utc_now
from verity_core.graph.dynamodb import items
from verity_core.graph.dynamodb.capacity import item_size, read_units, write_units
from verity_core.graph.dynamodb.table import TABLE_NAME
from verity_core.model.enums import EdgeType, NodeType

pytestmark = live_only


def stamped(record):
    now = utc_now()
    return record.model_copy(
        update={"created_at": now, "updated_at": now, "valid_from": now, "version": 1}
    )


def transact(client, *written):
    response = client.transact_write_items(
        TransactItems=[{"Put": {"TableName": TABLE_NAME, "Item": item}} for item in written],
        ReturnConsumedCapacity="INDEXES",
    )
    (consumed,) = response["ConsumedCapacity"]
    return consumed


def estimated(*written):
    return sum(write_units(item_size(item), transactional=True) for item in written)


def test_a_node_write_costs_what_capacity_estimates():
    node = stamped(probe_node(NodeType.AI_SYSTEM))
    written = (items.node_item(node), items.history_item(node))
    with probe_session() as client:
        consumed = transact(client, *written)
    print(f"\nRESULT node write: {consumed}")
    assert consumed["Table"]["CapacityUnits"] == estimated(*written) == 4


def test_an_edge_write_costs_what_capacity_estimates():
    system, model = probe_node(NodeType.AI_SYSTEM), probe_node(NodeType.MODEL)
    edge = stamped(make_edge(EdgeType.USES_MODEL, system.id, model.id, tenant=PROBE_TENANT))
    written = items.edge_items(edge)
    with probe_session() as client:
        consumed = transact(client, *written)
    print(f"\nRESULT edge write: {consumed}")
    assert consumed["Table"]["CapacityUnits"] == estimated(*written) == 4


def test_an_evidence_write_is_a_standard_write():
    item = items.node_item(stamped(evidence(tenant=PROBE_TENANT)))
    with probe_session() as client:
        response = client.put_item(
            TableName=TABLE_NAME, Item=item, ReturnConsumedCapacity="INDEXES"
        )
    consumed = response["ConsumedCapacity"]
    print(f"\nRESULT evidence write: {consumed}")
    assert consumed["Table"]["CapacityUnits"] == write_units(item_size(item))


def test_a_scan_costs_about_what_capacity_estimates():
    node = stamped(probe_node(NodeType.AI_SYSTEM))
    written = [items.node_item(node), items.history_item(node)]
    with probe_session() as client:
        transact(client, *written)
        response = client.scan(
            TableName=TABLE_NAME, ConsistentRead=True, ReturnConsumedCapacity="TOTAL"
        )
    consumed = response["ConsumedCapacity"]["CapacityUnits"]
    print(f"\nRESULT scan of {response['ScannedCount']} items: {consumed} units")
    sizes = [item_size(item) for item in response["Items"]]
    assert abs(consumed - read_units(sizes)) <= 1
