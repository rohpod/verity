"""Helpers for the tests that run against the real account (ADR 0015).

Nothing here runs unless `VERITY_LIVE_AWS=1` is set, so CI never touches AWS. Each run that
writes needs the owner's approval. Live tests write only under the fictional tenant
`m3-probe`, and remove what they wrote.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from factories import one_of_each
from verity_core.graph.dynamodb import keys
from verity_core.graph.dynamodb.client import default_client
from verity_core.graph.dynamodb.repository import DynamoDBRepository
from verity_core.graph.dynamodb.table import TABLE_NAME
from verity_core.model.enums import NodeType

PROBE_TENANT = "m3-probe"

live_only = pytest.mark.skipif(
    os.environ.get("VERITY_LIVE_AWS") != "1", reason="needs VERITY_LIVE_AWS=1 and approval"
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def probe_node(node_type: NodeType) -> Any:
    return one_of_each()[node_type].model_copy(update={"tenant": PROBE_TENANT})


def probe_repo(client: Any) -> DynamoDBRepository:
    return DynamoDBRepository(PROBE_TENANT, utc_now, client=client)


def probe_keys(client: Any) -> list[dict[str, Any]]:
    """The keys of every item under the probe tenant, and of nothing else."""
    found: list[dict[str, Any]] = []
    start: dict[str, Any] = {}
    while True:
        page = client.scan(
            TableName=TABLE_NAME,
            ProjectionExpression="PK, SK",
            FilterExpression="begins_with(PK, :tenant)",
            ExpressionAttributeValues={":tenant": {"S": keys.tenant_prefix(PROBE_TENANT)}},
            **start,
        )
        found += page.get("Items", [])
        if "LastEvaluatedKey" not in page:
            return found
        start = {"ExclusiveStartKey": page["LastEvaluatedKey"]}


def delete_probe_items(client: Any) -> int:
    found = probe_keys(client)
    for key in found:
        if not key["PK"]["S"].startswith(keys.tenant_prefix(PROBE_TENANT)):
            raise AssertionError(f"refusing to delete outside the probe tenant: {key}")
        client.delete_item(TableName=TABLE_NAME, Key=key)
    return len(found)


@contextmanager
def probe_session(client: Any = None) -> Iterator[Any]:
    """A client on a clean probe tenant. The tenant is emptied again even if the test fails."""
    client = client or default_client()
    delete_probe_items(client)
    try:
        yield client
    finally:
        delete_probe_items(client)
        assert probe_keys(client) == []
