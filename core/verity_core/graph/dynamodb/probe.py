"""A write that can never succeed, to show that IAM refuses it (ADR 0025, decision 5).

`verity-probe` runs on `support-assistant-role`, whose policy allows `PutItem` only where
`dynamodb:LeadingKeys` is that system's own usage partition. Each attempt here targets an item
outside it. The condition `attribute_exists(PK) AND attribute_not_exists(PK)` is never true, so
if IAM wrongly let a write through, DynamoDB would still refuse it and nothing would change. The
two outcomes then differ:

- `AccessDeniedException`: IAM refused it, so `LeadingKeys` holds.
- `ConditionalCheckFailedException`: IAM allowed it and the condition saved the item. The limit
  does not hold.

Only the error code is returned, never a message. One of the few modules allowed to import boto3.
"""

from typing import Any

from botocore.exceptions import ClientError

from verity_core.graph.dynamodb import keys

NEVER_TRUE = "attribute_exists(PK) AND attribute_not_exists(PK)"
ALLOWED = "Allowed"  # DynamoDB accepted the write. The condition makes this impossible.


def attempt_refused_writes(
    client: Any, table: str, tenant: str, system: str, other_system: str
) -> dict[str, str]:
    """Tries `PutItem` on the system's own `META` item and on another system's usage partition,
    and returns the error code of each, by name."""
    attempts = {
        "own_meta": (keys.node_pk(tenant, system), keys.META),
        "other_usage": (keys.usage_pk(tenant, other_system), "U#probe"),
    }
    return {name: _attempt(client, table, pk, sk) for name, (pk, sk) in attempts.items()}


def _attempt(client: Any, table: str, pk: str, sk: str) -> str:
    try:
        client.put_item(
            TableName=table,
            Item={"PK": {"S": pk}, "SK": {"S": sk}},
            ConditionExpression=NEVER_TRUE,
        )
    except ClientError as error:
        return str(error.response["Error"]["Code"])
    return ALLOWED
