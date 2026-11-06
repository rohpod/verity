"""A controllable clock for the telemetry tests."""

from datetime import UTC, datetime

import pytest

START = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock():
    return Clock()
