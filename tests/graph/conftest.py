from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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


@pytest.fixture(params=["memory", "dynamodb"])
def repo(request, clock):
    if request.param == "memory":
        yield InMemoryRepository(TENANT, clock)
        return
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        yield DynamoDBRepository(TENANT, clock, client=client)


@pytest.fixture
def estate(repo):
    from estate import load_estate

    load_estate(repo)
    return repo


@pytest.fixture
def estate_graph(estate):
    return estate.load_graph()


@pytest.fixture
def table():
    """A fresh moto table with its own clock, for tests that look inside DynamoDB."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        yield SimpleNamespace(client=client, clock=FakeClock())
