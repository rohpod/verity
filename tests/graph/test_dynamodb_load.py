"""`load_graph` on DynamoDB: one paged scan, and what it costs (ADR 0013)."""

import math
from datetime import timedelta
from uuid import uuid4

import pytest
from conftest import START
from dynamo_support import SpyClient, repo_for
from estate import load_estate
from factories import evidence, make_edge, one_of_each
from verity_core.graph.dynamodb import keys
from verity_core.graph.dynamodb.capacity import item_size, read_units
from verity_core.graph.dynamodb.table import TABLE_NAME, TABLE_RCU
from verity_core.model.enums import EdgeType, NodeType, Source
from verity_core.model.usage import UsageRecord

NODES = one_of_each()
PERSON, SYSTEM = NODES[NodeType.PERSON], NODES[NodeType.AI_SYSTEM]


def edges_in(graph):
    return sorted(
        (e.src, e.type.value, e.dst, e.qualifier or "") for _, _, e in graph.edges(data="record")
    )


def test_a_small_page_size_gives_the_same_graph(table):
    repo = repo_for(table)
    load_estate(repo)
    whole = repo.load_graph()
    spy = SpyClient(table.client)
    paged = repo_for(table, client=spy, scan_page_items=7).load_graph()
    assert sorted(paged.nodes) == sorted(whole.nodes) and edges_in(paged) == edges_in(whole)
    stored = len(table.client.scan(TableName=TABLE_NAME)["Items"])
    assert spy.calls["scan"] == math.ceil(stored / 7)


def test_every_scan_page_is_consistent_filtered_to_the_tenant_and_limited(table):
    spy = SpyClient(table.client)
    repo = repo_for(table, client=spy)
    load_estate(repo)
    spy.kwargs.clear()
    repo.load_graph()
    pages = spy.kwargs["scan"]
    assert pages and all(p["ConsistentRead"] is True and p["Limit"] == 100 for p in pages)
    assert all(p["ExpressionAttributeValues"] == {":tenant": {"S": "T#kestrel#"}} for p in pages)


def test_mirrors_and_usage_are_read_but_not_mistaken_for_graph_content(table):
    repo = repo_for(table)
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id))
    repo.append_usage(
        UsageRecord(
            tenant="kestrel",
            usage_id=uuid4(),
            system_id=SYSTEM.id,
            provider_id="prov:p",
            model_id="model:m",
            timestamp=START,
            token_estimate=1,
            source=Source.SIMULATED,
        )
    )
    graph = repo.load_graph()
    assert graph.number_of_nodes() == 2 and graph.number_of_edges() == 1  # not 2: no mirror twin


def test_a_usage_item_in_its_own_partition_is_scanned_past_and_breaks_nothing(table):
    repo = repo_for(table)
    repo.upsert_node(SYSTEM)
    table.client.put_item(
        TableName=TABLE_NAME,
        Item={
            "PK": {"S": keys.usage_pk("kestrel", SYSTEM.id)},
            "SK": {"S": "U#2026-11-05T09:00:00.000000Z#x"},
            "doc": {"S": "{}"},
        },
    )
    graph = repo.load_graph()
    assert list(graph.nodes) == [SYSTEM.id]


def test_another_tenants_items_are_scanned_past_not_loaded(table):
    mine, theirs = repo_for(table, "kestrel"), repo_for(table, "other")
    mine.upsert_node(SYSTEM)
    theirs.upsert_node(SYSTEM.model_copy(update={"tenant": "other"}))
    assert [d["record"].tenant for _, d in mine.load_graph().nodes(data=True)] == ["kestrel"]
    assert [d["record"].tenant for _, d in theirs.load_graph().nodes(data=True)] == ["other"]


def test_a_naive_as_of_is_refused_before_anything_is_scanned(table):
    spy = SpyClient(table.client)
    with pytest.raises(ValueError, match="timezone-aware"):
        repo_for(table, client=spy).load_graph(as_of=START.replace(tzinfo=None))
    assert spy.calls["scan"] == 0


def test_the_graph_at_each_day_shows_the_node_as_it_was_then(table):
    repo = repo_for(table)
    for day in range(1, 6):
        repo.upsert_node(SYSTEM.model_copy(update={"purpose": f"Purpose {day}"}))
        table.clock.advance(days=1)
    for day in range(1, 6):
        at = START + timedelta(days=day - 1, hours=12)
        assert repo.load_graph(as_of=at).nodes[SYSTEM.id]["record"].purpose == f"Purpose {day}"
    assert repo.load_graph().nodes[SYSTEM.id]["record"].purpose == "Purpose 5"


def test_evidence_has_no_history_items_but_still_appears_in_a_past_graph(table):
    repo = repo_for(table)
    stored = repo.upsert_node(evidence())
    table.clock.advance(days=3)
    found = table.client.scan(TableName=TABLE_NAME)["Items"]
    assert [keys.kind_of(i["SK"]["S"]) for i in found] == ["META"]
    assert stored.id in repo.load_graph(as_of=START + timedelta(days=1)).nodes


def test_a_past_graph_leaves_out_a_node_not_yet_written(table):
    repo = repo_for(table)
    table.clock.advance(days=2)
    repo.upsert_node(SYSTEM)
    assert SYSTEM.id not in repo.load_graph(as_of=START + timedelta(days=1)).nodes
    assert SYSTEM.id in repo.load_graph(as_of=START + timedelta(days=3)).nodes


# --- what a scan costs -----------------------------------------------------------------------


def scanned_sizes(table):
    return [item_size(i) for i in table.client.scan(TableName=TABLE_NAME)["Items"]]


def test_a_scan_page_asks_for_no_more_than_a_second_of_the_tables_read_capacity(table):
    repo = repo_for(table)
    load_estate(repo)
    sizes = scanned_sizes(table)
    for start in range(0, len(sizes), 100):
        assert read_units(sizes[start : start + 100]) <= TABLE_RCU, start


def test_loading_the_estate_costs_a_few_dozen_read_units(table):
    repo = repo_for(table)
    load_estate(repo)
    sizes = scanned_sizes(table)
    assert len(sizes) > 200 and max(sizes) < 1024  # every item is under 1 KB
    assert read_units(sizes) < 60  # about 29 when measured: 276 items, 117 KB


def test_about_half_of_what_a_plain_load_reads_is_ignored(table):
    # Mirrors, history and usage are read and thrown away (ADR 0014). This documents the waste
    # so a change is noticed.
    repo = repo_for(table)
    load_estate(repo)
    found = table.client.scan(TableName=TABLE_NAME)["Items"]
    ignored = sum(item_size(i) for i in found if keys.kind_of(i["SK"]["S"]) in ("R", "H", "U"))
    assert 0.4 < ignored / sum(item_size(i) for i in found) < 0.6
