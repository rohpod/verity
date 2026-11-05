"""What `DynamoDBRepository` does to the table for nodes (ADR 0013). The shared contract tests
cover behaviour; these cover items, atomicity, conflicts and the number of calls."""

from datetime import timedelta

import pytest
from botocore.exceptions import ClientError
from conftest import START
from dynamo_support import SpyClient, kinds_of, put_edge, repo_for
from factories import COMMON, TENANT, evidence, make_edge, one_of_each
from verity_core.graph.dynamodb import items, keys
from verity_core.graph.dynamodb.repository import (
    REGION,
    _is_conflict,
    default_client,
)
from verity_core.graph.dynamodb.table import TABLE_NAME
from verity_core.graph.errors import ConcurrentWriteError, InvalidEdgeError, RepositoryError
from verity_core.model import ids
from verity_core.model.enums import Direction, EdgeType, ModelOrigin, NodeType
from verity_core.model.nodes import Organisation

NODES = one_of_each()
SYSTEM = NODES[NodeType.AI_SYSTEM]
PERSON = NODES[NodeType.PERSON]
MODEL = NODES[NodeType.MODEL]
PROVIDER = NODES[NodeType.PROVIDER]


# --- what a write puts in the table --------------------------------------------------------


def test_a_new_node_is_a_meta_item_and_one_history_item(table):
    repo = repo_for(table)
    repo.upsert_node(SYSTEM)
    assert kinds_of(table, SYSTEM.id) == ["H", "META"]


def test_each_real_change_adds_one_history_item(table):
    repo = repo_for(table)
    repo.upsert_node(SYSTEM)
    table.clock.advance(days=1)
    repo.upsert_node(SYSTEM.model_copy(update={"purpose": "Changed"}))
    assert kinds_of(table, SYSTEM.id) == ["H", "H", "META"]
    meta = table.client.get_item(
        TableName=TABLE_NAME,
        Key={"PK": {"S": keys.node_pk(TENANT, SYSTEM.id)}, "SK": {"S": "META"}},
    )["Item"]
    assert meta["ver"] == {"N": "2"}


def test_resending_an_unchanged_node_writes_nothing(table):
    spy = SpyClient(table.client)
    repo = repo_for(table, client=spy)
    repo.upsert_node(SYSTEM)
    before = table.client.scan(TableName=TABLE_NAME)["Items"]
    writes = spy.calls["transact_write_items"] + spy.calls["put_item"]
    table.clock.advance(days=1)
    repo.upsert_node(SYSTEM)
    assert table.client.scan(TableName=TABLE_NAME)["Items"] == before  # not even updated_at
    assert spy.calls["transact_write_items"] + spy.calls["put_item"] == writes


def test_evidence_is_one_item_with_no_history_item(table):
    repo = repo_for(table)
    e = repo.upsert_node(evidence())
    assert kinds_of(table, e.id) == ["META"]
    repo.upsert_node(evidence())
    assert kinds_of(table, e.id) == ["META"]
    assert repo.history(e.id) == [e]  # read from META, since it never changes


def test_history_of_a_missing_node_is_empty_and_a_plain_node_is_never_read_from_meta(table):
    repo = repo_for(table)
    assert repo.history("sys:nope") == []
    repo.upsert_node(SYSTEM)
    assert [v.version for v in repo.history(SYSTEM.id)] == [1]


def test_history_stays_in_order_with_many_versions_at_one_instant(table):
    repo = repo_for(table)  # the clock never moves, so every version has the same timestamp
    repo.upsert_node(SYSTEM)
    for n in range(2, 13):
        repo.upsert_node(SYSTEM.model_copy(update={"purpose": f"Purpose {n}"}))
    assert [v.version for v in repo.history(SYSTEM.id)] == list(range(1, 13))


def test_the_stored_document_is_the_record(table):
    stored = repo_for(table).upsert_node(SYSTEM)
    item = table.client.get_item(
        TableName=TABLE_NAME,
        Key={"PK": {"S": keys.node_pk(TENANT, SYSTEM.id)}, "SK": {"S": "META"}},
    )["Item"]
    assert items.node_from_item(item) == stored
    assert item["GSI1PK"]["S"] == "T#kestrel#TYPE#AISystem" and item["GSI1SK"]["S"] == SYSTEM.id


# --- the number of calls a write makes -----------------------------------------------------


def test_a_plain_node_write_is_one_read_and_one_transaction(table):
    spy = SpyClient(table.client)
    repo_for(table, client=spy).upsert_node(PERSON)
    assert dict(spy.calls) == {"get_item": 1, "transact_write_items": 1}


def test_a_new_evidence_write_is_one_read_and_one_put(table):
    spy = SpyClient(table.client)
    repo_for(table, client=spy).upsert_node(evidence())
    assert dict(spy.calls) == {"get_item": 1, "put_item": 1}


def test_only_models_and_resources_read_edges_before_a_write(table):
    spy = SpyClient(table.client)
    repo = repo_for(table, client=spy)
    repo.upsert_node(SYSTEM)
    assert spy.calls["query"] == 0
    repo.upsert_node(MODEL)  # a model's origin can clash with an edge, so its edges are read
    assert spy.calls["query"] == 2  # outgoing and incoming


def test_the_organisation_rule_reads_the_type_index_only_for_an_organisation(table):
    spy = SpyClient(table.client)
    repo = repo_for(table, client=spy)
    repo.upsert_node(SYSTEM)
    assert spy.calls["query"] == 0
    repo.upsert_node(NODES[NodeType.ORGANISATION])
    assert spy.calls["query"] == 1


# --- stale and competing writes ------------------------------------------------------------


def test_a_stale_update_is_refused_and_leaves_nothing_behind(table):
    a, b = repo_for(table), repo_for(table)
    a.upsert_node(SYSTEM)
    stale = a.get_node(SYSTEM.id)
    b.upsert_node(SYSTEM.model_copy(update={"purpose": "B was first"}))  # version 2
    newer = stale.model_copy(update={"purpose": "A, from version 1", "version": 2})
    with pytest.raises(ConcurrentWriteError):
        a._write_node(newer, expected_version=1)
    assert kinds_of(table, SYSTEM.id) == ["H", "H", "META"]  # the failed write added no history
    assert b.get_node(SYSTEM.id).purpose == "B was first"


def test_inserting_over_an_existing_node_is_refused(table):
    repo = repo_for(table)
    stored = repo.upsert_node(SYSTEM)
    with pytest.raises(ConcurrentWriteError):
        repo._write_node(stored, expected_version=None)  # claims the node is new
    assert kinds_of(table, SYSTEM.id) == ["H", "META"]


def test_inserting_over_existing_evidence_is_refused(table):
    repo = repo_for(table)
    stored = repo.upsert_node(evidence())
    with pytest.raises(ConcurrentWriteError):
        repo._write_node(stored, expected_version=None)
    assert kinds_of(table, stored.id) == ["META"]


def test_a_competing_write_between_the_read_and_the_write_is_caught(table):
    spy = SpyClient(table.client)
    a, b = repo_for(table, client=spy), repo_for(table)
    a.upsert_node(SYSTEM)
    spy.before["transact_write_items"] = lambda: b.upsert_node(
        SYSTEM.model_copy(update={"purpose": "Won the race"})
    )
    with pytest.raises(ConcurrentWriteError):
        a.upsert_node(SYSTEM.model_copy(update={"purpose": "Lost the race"}))
    assert a.get_node(SYSTEM.id).purpose == "Won the race"
    assert [v.version for v in a.history(SYSTEM.id)] == [1, 2]
    a.upsert_node(SYSTEM.model_copy(update={"purpose": "Retried"}))  # a read-and-retry succeeds
    assert a.get_node(SYSTEM.id).version == 3


def test_two_writers_creating_the_same_node_leave_one_winner(table):
    spy = SpyClient(table.client)
    a, b = repo_for(table, client=spy), repo_for(table)
    spy.before["transact_write_items"] = lambda: b.upsert_node(SYSTEM)
    with pytest.raises(ConcurrentWriteError):
        a.upsert_node(SYSTEM)
    assert kinds_of(table, SYSTEM.id) == ["H", "META"]


def test_other_aws_errors_are_not_mistaken_for_conflicts(table):
    missing = repo_for(table, table_name="no-such-table")
    with pytest.raises(ClientError) as caught:
        missing.upsert_node(SYSTEM)
    assert caught.value.response["Error"]["Code"] == "ResourceNotFoundException"


def aws_error(code, reasons=None):
    response = {"Error": {"Code": code, "Message": "x"}}
    if reasons is not None:
        response["CancellationReasons"] = [{"Code": r} for r in reasons]
    return ClientError(response, "TransactWriteItems")


@pytest.mark.parametrize(
    "error,is_conflict",
    [
        (aws_error("ConditionalCheckFailedException"), True),
        (aws_error("TransactionCanceledException", ["ConditionalCheckFailed", "None"]), True),
        (aws_error("TransactionCanceledException", ["None", "TransactionConflict"]), True),
        (aws_error("TransactionCanceledException", ["ThrottlingError"]), False),
        (aws_error("TransactionCanceledException", ["ValidationError"]), False),
        (aws_error("TransactionCanceledException"), False),
        (aws_error("ProvisionedThroughputExceededException"), False),
        (aws_error("ValidationException"), False),
    ],
)
def test_only_lost_races_are_treated_as_conflicts(error, is_conflict):
    # A cancellation for throttling or a bad request is not a conflict: retrying the read would
    # hide it, so those errors must reach the caller unchanged.
    assert _is_conflict(error) is is_conflict


# --- listing by type -----------------------------------------------------------------------


def test_listing_by_type_fetches_every_node_in_batches_and_sorts_them(table):
    repo = repo_for(table)
    for n in range(120):  # more than one BatchGetItem of 100
        repo.upsert_node(SYSTEM.model_copy(update={"id": ids.system_id(f"s{n:03d}")}))
    spy = SpyClient(table.client)
    listed = repo_for(table, client=spy).nodes_by_type(NodeType.AI_SYSTEM)
    assert [n.id for n in listed] == [f"sys:s{n:03d}" for n in range(120)]
    assert spy.calls["batch_get_item"] == 2 and spy.calls["query"] == 1


def test_the_type_index_holds_keys_only_and_lists_only_current_versions(table):
    repo = repo_for(table)
    repo.upsert_node(SYSTEM)
    repo.upsert_node(SYSTEM.model_copy(update={"purpose": "Changed"}))  # two H# items now
    listed = table.client.query(
        TableName=TABLE_NAME,
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :p",
        ExpressionAttributeValues={":p": {"S": "T#kestrel#TYPE#AISystem"}},
    )["Items"]
    assert len(listed) == 1 and "doc" not in listed[0] and "ver" not in listed[0]


class ReversedBatch(SpyClient):
    """DynamoDB makes no promise about the order of `BatchGetItem` results; moto keeps it."""

    def batch_get_item(self, **kwargs):
        response = self._inner.batch_get_item(**kwargs)
        for found in response["Responses"].values():
            found.reverse()
        return response


def test_listing_by_type_does_not_depend_on_the_order_batch_results_arrive_in(table):
    repo = repo_for(table)
    for slug in ("b", "c", "a"):
        repo.upsert_node(SYSTEM.model_copy(update={"id": ids.system_id(slug)}))
    shuffled = repo_for(table, client=ReversedBatch(table.client))
    assert [n.id for n in shuffled.nodes_by_type(NodeType.AI_SYSTEM)] == ["sys:a", "sys:b", "sys:c"]


class SmallPages(SpyClient):
    """Returns two items per query page, as DynamoDB does once a page reaches 1 MB."""

    def query(self, **kwargs):
        self.calls["query"] += 1
        return self._inner.query(Limit=2, **kwargs)


def test_every_page_of_a_long_partition_is_read(table):
    repo = repo_for(table)
    repo.upsert_node(SYSTEM)
    for n in range(2, 8):
        repo.upsert_node(SYSTEM.model_copy(update={"purpose": f"Purpose {n}"}))
    paged = SmallPages(table.client)
    assert [v.version for v in repo_for(table, client=paged).history(SYSTEM.id)] == list(
        range(1, 8)
    )
    assert paged.calls["query"] >= 4


def test_every_page_of_the_type_index_is_read(table):
    repo = repo_for(table)
    for n in range(7):
        repo.upsert_node(SYSTEM.model_copy(update={"id": ids.system_id(f"s{n}")}))
    listed = repo_for(table, client=SmallPages(table.client)).nodes_by_type(NodeType.AI_SYSTEM)
    assert len(listed) == 7


class UnprocessedBatch(SpyClient):
    """Answers only the first half of a batch, as DynamoDB can under load."""

    def __init__(self, inner, rounds):
        super().__init__(inner)
        self.rounds = rounds

    def batch_get_item(self, RequestItems):
        self.calls["batch_get_item"] += 1
        ((name, request),) = RequestItems.items()
        if self.rounds == 0:
            return self._inner.batch_get_item(RequestItems=RequestItems)
        self.rounds -= 1
        keys_ = request["Keys"]
        half = max(len(keys_) // 2, 0)
        done = (
            self._inner.batch_get_item(RequestItems={name: {**request, "Keys": keys_[:half]}})
            if half
            else {"Responses": {}}
        )
        return {
            "Responses": done.get("Responses", {}),
            "UnprocessedKeys": {name: {**request, "Keys": keys_[half:]}},
        }


def test_unprocessed_keys_are_fetched_again_with_a_growing_pause(table):
    repo = repo_for(table)
    for n in range(8):
        repo.upsert_node(SYSTEM.model_copy(update={"id": ids.system_id(f"s{n}")}))
    pauses = []
    flaky = repo_for(table, client=UnprocessedBatch(table.client, rounds=3), sleep=pauses.append)
    assert [n.id for n in flaky.nodes_by_type(NodeType.AI_SYSTEM)] == [
        f"sys:s{n}" for n in range(8)
    ]
    assert len(pauses) == 3 and pauses == sorted(pauses) and pauses[0] < pauses[-1]


def test_keys_that_never_come_back_are_reported_not_dropped(table):
    repo = repo_for(table)
    repo.upsert_node(SYSTEM)
    pauses = []
    stuck = repo_for(table, client=UnprocessedBatch(table.client, rounds=99), sleep=pauses.append)
    with pytest.raises(RepositoryError, match="unprocessed"):
        stuck.nodes_by_type(NodeType.AI_SYSTEM)
    assert max(pauses) <= 2.0


# --- tenants share the table but not the data ----------------------------------------------


def test_two_tenants_in_one_table_never_see_each_other(table):
    mine, theirs = repo_for(table, "kestrel"), repo_for(table, "other")
    mine.upsert_node(SYSTEM)
    other_system = SYSTEM.model_copy(update={"tenant": "other", "purpose": "Theirs"})
    theirs.upsert_node(other_system)  # the same ID, in another tenant
    assert mine.get_node(SYSTEM.id).purpose != "Theirs"
    assert theirs.get_node(SYSTEM.id).purpose == "Theirs"
    assert [n.tenant for n in mine.nodes_by_type(NodeType.AI_SYSTEM)] == ["kestrel"]
    assert [n.tenant for n in theirs.nodes_by_type(NodeType.AI_SYSTEM)] == ["other"]
    assert len(mine.history(SYSTEM.id)) == len(theirs.history(SYSTEM.id)) == 1


def test_each_tenant_can_have_its_own_organisation(table):
    org = NODES[NodeType.ORGANISATION]
    repo_for(table, "kestrel").upsert_node(org)
    repo_for(table, "other").upsert_node(org.model_copy(update={"tenant": "other"}))
    second = Organisation(id=ids.organisation_id("extra"), name="Extra", **COMMON)
    from verity_core.graph.errors import InvalidNodeError

    with pytest.raises(InvalidNodeError):
        repo_for(table, "kestrel").upsert_node(second)


# --- reading edges (writes arrive in the next PR) ------------------------------------------


def test_neighbors_read_outgoing_and_incoming_items_in_key_order(table):
    repo = repo_for(table)
    owns_system = make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id)
    owns_risk = make_edge(EdgeType.OWNS, PERSON.id, "risk:screening-bias")
    has_risk = make_edge(EdgeType.HAS_RISK, SYSTEM.id, "risk:screening-bias")
    for edge in (owns_system, owns_risk, has_risk):
        put_edge(table, edge)
    assert [e.dst for e in repo.neighbors(PERSON.id, Direction.OUT)] == [
        "risk:screening-bias",
        SYSTEM.id,
    ]
    assert repo.neighbors(PERSON.id, Direction.OUT, EdgeType.HAS_RISK) == []
    assert repo.neighbors(SYSTEM.id, Direction.IN) == [owns_system]
    assert repo.neighbors(SYSTEM.id, Direction.OUT, EdgeType.HAS_RISK) == [has_risk]
    assert repo.neighbors("sys:nope", Direction.OUT) == []


def test_neighbors_respect_validity(table):
    repo = repo_for(table)
    past = make_edge(
        EdgeType.OWNS,
        PERSON.id,
        SYSTEM.id,
        valid_from=START - timedelta(days=9),
        valid_to=START - timedelta(days=1),
    )
    put_edge(table, past)
    assert repo.neighbors(PERSON.id, Direction.OUT) == []
    assert repo.neighbors(PERSON.id, Direction.OUT, as_of=START - timedelta(days=5)) == [past]
    with pytest.raises(ValueError, match="timezone-aware"):
        repo.neighbors(PERSON.id, Direction.OUT, as_of=START.replace(tzinfo=None))


def test_a_model_cannot_become_in_house_while_it_has_a_provider(table):
    repo = repo_for(table)
    third_party = MODEL.model_copy(update={"origin": ModelOrigin.THIRD_PARTY})
    repo.upsert_node(third_party)
    put_edge(table, make_edge(EdgeType.PROVIDED_BY, third_party.id, PROVIDER.id))
    with pytest.raises(InvalidEdgeError) as caught:
        repo.upsert_node(third_party.model_copy(update={"origin": ModelOrigin.IN_HOUSE}))
    assert caught.value.rule == "provided_by_third_party_only"
    assert repo.get_node(third_party.id).origin is ModelOrigin.THIRD_PARTY
    assert len(repo.history(third_party.id)) == 1


# --- the client ----------------------------------------------------------------------------


def test_the_default_client_retries_throttling_with_backoff_in_the_one_region(table):
    client = default_client()
    assert client.meta.config.retries == {"mode": "standard", "total_max_attempts": 10}
    assert client.meta.region_name == "eu-north-1" == REGION
