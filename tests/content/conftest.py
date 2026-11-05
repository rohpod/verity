"""A clock and a repository on each backend, for the tests that seed content."""

from datetime import UTC, datetime

import boto3
import pytest
from factories import TENANT
from moto import mock_aws
from verity_core.graph.dynamodb.repository import DynamoDBRepository
from verity_core.graph.dynamodb.table import table_definition
from verity_core.graph.memory import InMemoryRepository

START = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture(params=["memory", "dynamodb"])
def repo(request, clock):
    if request.param == "memory":
        yield InMemoryRepository(TENANT, clock)
        return
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        yield DynamoDBRepository(TENANT, clock, client=client)
