"""`DynamoDBUsageSink`: what the `verity_ai` adapters write through (D8, ADR 0013).

It is one conditional `PutItem` in the system's own usage partition. It never reads, so an app role
needs only `dynamodb:PutItem`, limited to its partition with `dynamodb:LeadingKeys`. The graph
repository delegates to it. One of the few modules allowed to import boto3.
"""

from typing import Any

from botocore.exceptions import ClientError

from verity_core.graph.dynamodb import items
from verity_core.graph.dynamodb.client import default_client
from verity_core.graph.dynamodb.table import TABLE_NAME
from verity_core.graph.planning import ensure_tenant
from verity_core.model.usage import UsageRecord


class DynamoDBUsageSink:
    def __init__(self, tenant: str, *, client: Any = None, table_name: str = TABLE_NAME):
        self.tenant = tenant
        self._client = client if client is not None else default_client()
        self._table = table_name

    def append_usage(self, record: UsageRecord) -> None:
        """Append-only. The key is the system, the timestamp and `usage_id`, so a retried write
        meets its own earlier item and is left alone: the first write wins."""
        ensure_tenant(self.tenant, record.tenant, "usage record")
        try:
            self._client.put_item(
                TableName=self._table,
                Item=items.usage_item(record),
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
