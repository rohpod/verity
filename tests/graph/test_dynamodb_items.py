import ast
import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import START
from factories import COMMON, evidence, make_edge
from verity_core.graph.dynamodb import items, keys, table
from verity_core.model.enums import EdgeType, NodeType, Source
from verity_core.model.usage import UsageRecord


def all_nodes(repo):
    return [n for t in NodeType for n in repo.nodes_by_type(t)]


def all_edges(repo):
    return [e for _, _, e in repo.load_graph().edges(data="record")]


def test_every_estate_node_round_trips_through_its_item(estate):
    for node in all_nodes(estate):
        assert items.node_from_item(items.node_item(node)) == node


def test_every_estate_edge_round_trips_through_both_of_its_items(estate):
    for edge in all_edges(estate):
        forward, reverse = items.edge_items(edge)
        assert items.edge_from_item(forward) == edge == items.edge_from_item(reverse)


def test_a_node_item_carries_its_keys_version_and_listing_keys(estate):
    node = estate.get_node("sys:talent-screening")
    item = items.node_item(node)
    assert item["PK"] == {"S": "T#kestrel#N#sys:talent-screening"} and item["SK"] == {"S": "META"}
    assert item["ver"] == {"N": str(node.version)}
    assert item["GSI1PK"] == {"S": "T#kestrel#TYPE#AISystem"}
    assert item["GSI1SK"] == {"S": node.id}


def test_only_the_meta_item_is_listed_by_type(estate):
    node = estate.get_node("sys:talent-screening")
    history = items.history_item(node)
    assert "GSI1PK" not in history and "GSI1SK" not in history
    forward, reverse = items.edge_items(all_edges(estate)[0])
    assert not {"GSI1PK", "GSI1SK"} & (set(forward) | set(reverse))


def test_a_history_item_is_keyed_by_when_and_which_version(estate):
    node = estate.get_node("sys:talent-screening")
    item = items.history_item(node)
    assert item["SK"]["S"] == keys.history_sk(node.updated_at, node.version)
    assert items.node_from_item(item) == node
    with pytest.raises(ValueError, match="stored node"):
        items.history_item(node.model_copy(update={"updated_at": None}))


def test_an_edge_and_its_mirror_share_a_document_and_a_version(estate):
    edge = next(e for e in all_edges(estate) if e.qualifier)
    forward, reverse = items.edge_items(edge)
    assert forward["doc"] == reverse["doc"] and forward["ver"] == reverse["ver"]
    assert forward["PK"]["S"] == keys.node_pk("kestrel", edge.src)
    assert reverse["PK"]["S"] == keys.node_pk("kestrel", edge.dst)
    assert forward["SK"]["S"] == keys.edge_sk(edge.key)
    assert reverse["SK"]["S"] == keys.reverse_sk(edge.key)


def test_closed_intervals_survive_the_item(estate):
    estate.close_edge("person:l-ivanova", EdgeType.OWNS, "sys:contract-insights", valid_to=START)
    reopened = estate.upsert_edge(
        make_edge(EdgeType.OWNS, "person:l-ivanova", "sys:contract-insights")
    )
    forward, _ = items.edge_items(reopened)
    assert items.edge_from_item(forward).closed_intervals == reopened.closed_intervals


def usage(**overrides):
    fields = {
        "tenant": COMMON["tenant"],
        "usage_id": uuid4(),
        "system_id": "sys:support-assistant",
        "provider_id": "prov:mock-bedrock",
        "model_id": "model:fm-1",
        "timestamp": START,
        "token_estimate": 120,
        "source": Source.SIMULATED,
    } | overrides
    return UsageRecord(**fields)


def test_a_usage_item_round_trips_and_lives_in_the_usage_partition():
    record = usage()
    item = items.usage_item(record)
    assert items.usage_from_item(item) == record
    assert item["PK"]["S"] == keys.usage_pk("kestrel", record.system_id)
    assert item["SK"]["S"] == keys.usage_sk(record.timestamp, record.usage_id)
    assert {"ver", "GSI1PK"}.isdisjoint(item)


def test_numbers_inside_evidence_survive_unchanged():
    # boto3 turns stored numbers into Decimal. A JSON string avoids that and keeps the hash.
    content = {
        "int": 7,
        "big": 2**53 + 1,
        "float": 1.5,
        "neg": -0.25,
        "nested": [1, {"x": 2.0}],
        "é": "ü",
    }
    node = evidence(content=content)
    again = items.node_from_item(items.node_item(node))
    assert again.content == content and again.sha256 == node.sha256 and again == node


def test_items_hold_only_typed_strings_and_numbers():
    for item in (
        *items.edge_items(make_edge(EdgeType.OWNS, "person:a", "sys:b")),
        items.usage_item(usage()),
    ):
        for attribute, value in item.items():
            assert list(value) in (["S"], ["N"]), attribute
            assert not any(isinstance(v, Decimal | float) for v in value.values())


def test_the_document_is_the_records_json(estate):
    node = estate.get_node("sys:talent-screening")
    assert json.loads(items.node_item(node)["doc"]["S"]) == node.model_dump(mode="json")


def test_a_tampered_document_is_refused_when_read(estate):
    item = items.node_item(evidence())
    doc = json.loads(item["doc"]["S"])
    doc["content"]["runtime"] = "tampered"
    item["doc"] = {"S": json.dumps(doc)}
    with pytest.raises(ValueError, match="does not match"):
        items.node_from_item(item)


def imported_modules(module) -> set[str]:
    tree = ast.parse(Path(module.__file__).read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_storage_modules_import_no_aws_library():
    for module in (keys, items, table):
        assert not {"boto3", "botocore", "moto"} & imported_modules(module), module.__name__
