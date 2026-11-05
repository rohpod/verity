"""The `verity-graph` table, described once (CLAUDE.md hard constraint 1, ADR 0003).

Provisioned capacity and the Standard table class are the only combination inside the Always
Free allowance. The capacity is split table 15/15 and GSI1 10/10, which totals 25/25, and
auto-scaling stays off. The tests build the table from this, and M3's OpenTofu must match it.
"""

from typing import Any

from verity_core.graph.dynamodb.keys import GSI1

TABLE_NAME = "verity-graph"

TABLE_RCU = 15
TABLE_WCU = 15
GSI_RCU = 10
GSI_WCU = 10
FREE_ALLOWANCE_UNITS = 25  # read and write capacity units, each, across table and indexes


def table_definition(name: str = TABLE_NAME) -> dict[str, Any]:
    """Keyword arguments for `create_table`."""
    return {
        "TableName": name,
        "BillingMode": "PROVISIONED",
        "TableClass": "STANDARD",
        "AttributeDefinitions": [
            {"AttributeName": attribute, "AttributeType": "S"}
            for attribute in ("PK", "SK", "GSI1PK", "GSI1SK")
        ],
        "KeySchema": [
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        "ProvisionedThroughput": {"ReadCapacityUnits": TABLE_RCU, "WriteCapacityUnits": TABLE_WCU},
        "GlobalSecondaryIndexes": [
            {
                "IndexName": GSI1,
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                # Keys only (D14): listing by type reads the index, then fetches the nodes.
                "Projection": {"ProjectionType": "KEYS_ONLY"},
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": GSI_RCU,
                    "WriteCapacityUnits": GSI_WCU,
                },
            }
        ],
    }
