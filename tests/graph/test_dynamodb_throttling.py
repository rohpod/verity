"""A transaction cancelled for lack of capacity is retried; one cancelled by a conflict is not.

boto3 does not retry a `TransactionCanceledException`, so the repository does (D14). moto
cannot throttle, so these cancellations are injected."""

import pytest
from botocore.exceptions import ClientError
from conftest import START
from dynamo_support import SpyClient, aws_failure, cancelled, kinds_of, repo_for, rows
from factories import make_edge, one_of_each
from verity_core.graph.dynamodb import repository as module
from verity_core.graph.dynamodb.repository import _is_throttle
from verity_core.graph.errors import ConcurrentWriteError
from verity_core.model import ids
from verity_core.model.enums import Direction, EdgeType, NodeType

NODES = one_of_each()
SYSTEM, PERSON = NODES[NodeType.AI_SYSTEM], NODES[NodeType.PERSON]
THROTTLE = ("ProvisionedThroughputExceeded", "None")


@pytest.mark.parametrize(
    "error,expected",
    [
        (cancelled("ProvisionedThroughputExceeded", "None"), True),
        (cancelled("None", "ThrottlingError"), True),
        (cancelled("ProvisionedThroughputExceeded", "ProvisionedThroughputExceeded"), True),
        (cancelled("ProvisionedThroughputExceeded", "ConditionalCheckFailed"), False),
        (cancelled("ThrottlingError", "TransactionConflict"), False),
        (cancelled("ConditionalCheckFailed", "None"), False),
        (cancelled("ValidationError", "None"), False),
        (cancelled("None", "None"), False),
        (aws_failure("ProvisionedThroughputExceededException"), False),  # boto3 retries these
        (aws_failure("ValidationException"), False),
    ],
)
def test_only_a_cancellation_caused_purely_by_throttling_is_retried(error, expected):
    assert _is_throttle(error) is expected


def test_a_throttled_write_is_repeated_and_lands_exactly_once(table):
    spy = SpyClient(table.client)
    pauses = []
    spy.fail[("transact_write_items", 1)] = cancelled(*THROTTLE)
    repo = repo_for(table, client=spy, sleep=pauses.append)
    stored = repo.upsert_node(SYSTEM)
    assert stored.version == 1 and spy.calls["transact_write_items"] == 2
    assert pauses == [0.2]
    assert kinds_of(table, SYSTEM.id) == ["H", "META"]  # the cancelled attempt wrote nothing


def test_the_pauses_double_up_to_a_cap(table):
    spy = SpyClient(table.client)
    pauses = []
    for call in range(1, 8):
        spy.fail[("transact_write_items", call)] = cancelled(*THROTTLE)
    repo_for(table, client=spy, sleep=pauses.append).upsert_node(SYSTEM)  # succeeds on the 8th
    assert pauses == [0.2, 0.4, 0.8, 1.6, 3.2, 6.4, 10.0]
    assert 20 < sum(pauses) < 25  # long enough for a 15-unit table to refill a 50-edge chunk


def test_a_write_that_stays_throttled_gives_up_with_the_original_error(table):
    spy = SpyClient(table.client)
    pauses = []
    for call in range(1, 20):
        spy.fail[("transact_write_items", call)] = cancelled(*THROTTLE)
    repo = repo_for(table, client=spy, sleep=pauses.append)
    with pytest.raises(ClientError) as caught:
        repo.upsert_node(SYSTEM)
    assert caught.value.response["Error"]["Code"] == "TransactionCanceledException"
    assert spy.calls["transact_write_items"] == 8 and len(pauses) == 7
    assert rows(table) == []


@pytest.mark.parametrize(
    "reasons",
    [
        ("ConditionalCheckFailed", "None"),
        ("ProvisionedThroughputExceeded", "ConditionalCheckFailed"),
    ],
)
def test_a_conflict_is_never_retried_even_alongside_throttling(table, reasons):
    spy = SpyClient(table.client)
    pauses = []
    spy.fail[("transact_write_items", 1)] = cancelled(*reasons)
    repo = repo_for(table, client=spy, sleep=pauses.append)
    with pytest.raises(ConcurrentWriteError):
        repo.upsert_node(SYSTEM)
    assert spy.calls["transact_write_items"] == 1 and pauses == []


def test_other_failures_are_not_retried(table):
    spy = SpyClient(table.client)
    pauses = []
    spy.fail[("transact_write_items", 1)] = cancelled("ValidationError", "None")
    with pytest.raises(ClientError):
        repo_for(table, client=spy, sleep=pauses.append).upsert_node(SYSTEM)
    assert spy.calls["transact_write_items"] == 1 and pauses == []


def test_a_retry_checks_the_condition_again_so_it_cannot_overwrite_a_newer_write(table):
    other = repo_for(table)

    def wait(_seconds):
        # Another writer changes the node while this one is waiting to retry.
        other.upsert_node(SYSTEM.model_copy(update={"purpose": "Written while A was waiting"}))

    spy = SpyClient(table.client)
    a = repo_for(table, client=spy, sleep=wait)
    a.upsert_node(SYSTEM)
    spy.fail[("transact_write_items", spy.calls["transact_write_items"] + 1)] = cancelled(*THROTTLE)
    with pytest.raises(ConcurrentWriteError):
        a.upsert_node(SYSTEM.model_copy(update={"purpose": "A's stale change"}))
    assert a.get_node(SYSTEM.id).purpose == "Written while A was waiting"


def test_edges_are_retried_too_and_stay_a_consistent_pair(table):
    spy = SpyClient(table.client)
    repo = repo_for(table, client=spy, sleep=lambda _: None)
    repo.upsert_node(PERSON)
    repo.upsert_node(SYSTEM)
    spy.fail[("transact_write_items", spy.calls["transact_write_items"] + 1)] = cancelled(
        "None", "ProvisionedThroughputExceeded"
    )
    edge = repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, SYSTEM.id))
    assert repo.neighbors(PERSON.id, Direction.OUT) == [edge]
    assert repo.neighbors(SYSTEM.id, Direction.IN) == [edge]


def test_a_throttled_chunk_of_a_cascade_is_retried_where_a_server_error_is_not(table):
    spy = SpyClient(table.client)
    repo = repo_for(table, client=spy, sleep=lambda _: None)
    repo.upsert_node(PERSON)
    for n in range(60):  # two chunks of edges
        system = SYSTEM.model_copy(update={"id": ids.system_id(f"s{n:02d}")})
        repo.upsert_node(system)
        repo.upsert_edge(make_edge(EdgeType.OWNS, PERSON.id, system.id))
    table.clock.advance(days=1)
    ended = PERSON.model_copy(update={"valid_from": START, "valid_to": table.clock.now})
    spy.fail[("transact_write_items", spy.calls["transact_write_items"] + 2)] = cancelled(*THROTTLE)
    repo.upsert_node(ended)  # the second chunk is throttled once, and the call still completes
    assert repo.get_node(PERSON.id).valid_to == table.clock.now
    assert repo.neighbors(PERSON.id, Direction.OUT) == []


def test_the_retry_limits_are_the_documented_ones():
    assert module._TRANSACTION_ATTEMPTS == 8
    assert (module._TRANSACTION_PAUSE, module._TRANSACTION_PAUSE_CAP) == (0.2, 10.0)
    assert {"ProvisionedThroughputExceeded", "ThrottlingError"} == module._THROTTLE_REASONS
