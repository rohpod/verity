from datetime import UTC, datetime, timedelta

import boto3
import pytest
from factories import TENANT
from moto import mock_aws
from verity_core.graph.dynamodb.repository import DynamoDBRepository
from verity_core.graph.dynamodb.table import table_definition
from verity_core.graph.memory import InMemoryRepository

START = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


class FakeClock:
    """A controllable clock, so tests never depend on real time."""

    def __init__(self, now: datetime = START):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    return FakeClock()


class SkipUntilImplemented:
    """Scaffolding for the M2 PRs, removed in PR 6. `DynamoDBRepository` is built over several
    PRs; until it has a method, a test that needs it is skipped instead of failing. PR 6 deletes
    this wrapper and the repository stops raising `NotImplementedError`, so every contract test
    must then run."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        attribute = getattr(self._inner, name)
        if not callable(attribute):
            return attribute

        def call(*args, **kwargs):
            try:
                return attribute(*args, **kwargs)
            except NotImplementedError as missing:
                pytest.skip(f"DynamoDBRepository.{name}: {missing}")

        return call


def unwrap(repo):
    """The real repository behind `SkipUntilImplemented`, for `isinstance` checks, which Python
    3.12 makes on the object itself without calling `__getattr__`. Removed with the wrapper."""
    return getattr(repo, "_inner", repo)


@pytest.fixture(params=["memory", "dynamodb"])
def repo(request, clock):
    if request.param == "memory":
        yield InMemoryRepository(TENANT, clock)
        return
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        yield SkipUntilImplemented(DynamoDBRepository(TENANT, clock, client=client))


@pytest.fixture
def estate(repo):
    from estate import load_estate

    load_estate(repo)
    return repo


@pytest.fixture
def estate_graph(estate):
    return estate.load_graph()
