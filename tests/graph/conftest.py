from datetime import UTC, datetime, timedelta

import pytest
from factories import TENANT
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


# M2 adds a "dynamodb" parameter here, so the whole contract suite runs on both repositories.
@pytest.fixture(params=["memory"])
def repo(request, clock):
    return InMemoryRepository(TENANT, clock)


@pytest.fixture
def estate(repo):
    from estate import load_estate

    load_estate(repo)
    return repo


@pytest.fixture
def estate_graph(estate):
    return estate.load_graph()
