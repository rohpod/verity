"""Helpers for the DynamoDB tests: a client that counts and interferes, and table readers."""

from collections import Counter

from botocore.exceptions import ClientError
from conftest import TENANT
from verity_core.graph.dynamodb import items, keys
from verity_core.graph.dynamodb.repository import DynamoDBRepository
from verity_core.graph.dynamodb.table import TABLE_NAME


def aws_failure(code="InternalServerError", operation="TransactWriteItems"):
    return ClientError({"Error": {"Code": code, "Message": "simulated"}}, operation)


class SpyClient:
    """Wraps a client to count calls, and to run a hook just before one."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = Counter()
        self.before = {}
        self.fail = {}  # (operation, call number) -> the error to raise on that call

    def __getattr__(self, name):
        attribute = getattr(self._inner, name)
        if not callable(attribute):
            return attribute

        def call(*args, **kwargs):
            self.calls[name] += 1
            error = self.fail.pop((name, self.calls[name]), None)
            if error:
                raise error
            hook = self.before.pop(name, None)
            if hook:
                hook()
            return attribute(*args, **kwargs)

        return call


def repo_for(table, tenant=TENANT, client=None, **kwargs):
    return DynamoDBRepository(tenant, table.clock, client=client or table.client, **kwargs)


def rows(table):
    """Every (PK, SK) in the table."""
    found, start = [], {}
    while True:
        page = table.client.scan(TableName=TABLE_NAME, **start)
        found += [(i["PK"]["S"], i["SK"]["S"]) for i in page["Items"]]
        if "LastEvaluatedKey" not in page:
            return sorted(found)
        start = {"ExclusiveStartKey": page["LastEvaluatedKey"]}


def kinds_of(table, node_id):
    pk = keys.node_pk(TENANT, node_id)
    return sorted(keys.kind_of(sk) for p, sk in rows(table) if p == pk)


def put_edge(table, edge):
    for item in items.edge_items(edge):
        table.client.put_item(TableName=TABLE_NAME, Item=item)
