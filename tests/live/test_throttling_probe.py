"""How the real table reports a transaction that runs out of capacity (the M3 note in
docs/stage-4-milestones.md). AWS's pages list two forms and do not say which one applies.

Capacity is provisioned and auto-scaling is off, so throttling costs nothing. Every transaction
overwrites the same keys, so at most `ITEMS` large items exist, and the session removes them.
"""

import json
import time

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError
from live_support import PROBE_TENANT, live_only, probe_node, probe_repo, probe_session
from verity_core.graph.dynamodb import keys
from verity_core.graph.dynamodb.client import REGION
from verity_core.graph.dynamodb.repository import _is_throttle
from verity_core.graph.dynamodb.table import TABLE_NAME
from verity_core.model.enums import NodeType

pytestmark = live_only

ITEMS = 20
ITEM_BYTES = 100 * 1024  # 20 items of 100 KB is about 4,000 write units a transaction
MAX_TRANSACTIONS = 8  # the table keeps about 4,500 units of burst, so this is enough


def large_writes() -> list[dict]:
    return [
        {
            "Put": {
                "TableName": TABLE_NAME,
                "Item": {
                    "PK": {"S": keys.node_pk(PROBE_TENANT, f"sys:probe-{number}")},
                    "SK": {"S": "PROBE"},
                    "doc": {"S": "x" * ITEM_BYTES},
                },
            }
        }
        for number in range(ITEMS)
    ]


def first_throttle(client) -> ClientError | None:
    writes = large_writes()
    for _ in range(MAX_TRANSACTIONS):
        try:
            client.transact_write_items(TransactItems=writes)
        except ClientError as error:
            return error
    return None


def test_a_throttled_transaction_is_a_form_the_repository_handles():
    no_retries = boto3.client(
        "dynamodb",
        region_name=REGION,
        config=Config(retries={"mode": "standard", "total_max_attempts": 1}),
    )
    with probe_session() as client:
        error = first_throttle(no_retries)
        if error is None:
            pytest.fail(f"no throttle after {MAX_TRANSACTIONS} transactions")
        code = error.response["Error"]["Code"]
        reasons = sorted({r.get("Code") for r in error.response.get("CancellationReasons", [])})
        print(f"\nRESULT throttle: {json.dumps({'code': code, 'reasons': reasons})}")
        if code == "TransactionCanceledException":
            assert _is_throttle(error), "the repository would not retry this"
        else:
            assert code == "ProvisionedThroughputExceededException", "boto3 would not retry this"

        started = time.monotonic()
        probe_repo(client).upsert_node(probe_node(NodeType.AI_SYSTEM))
        print(f"RESULT repository write after the throttle: {time.monotonic() - started:.1f} s")
