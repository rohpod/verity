"""The cleanup is what stands between a live test and real data, so it is tested offline."""

import boto3
from live_support import PROBE_TENANT, delete_probe_items, probe_keys, probe_session
from moto import mock_aws
from verity_core.graph.dynamodb import keys
from verity_core.graph.dynamodb.table import TABLE_NAME, table_definition


def put(client, tenant, node_id):
    item = {"PK": {"S": keys.node_pk(tenant, node_id)}, "SK": {"S": keys.META}}
    client.put_item(TableName=TABLE_NAME, Item=item)


def fresh_client():
    client = boto3.client("dynamodb", region_name="eu-north-1")
    client.create_table(**table_definition())
    return client


@mock_aws
def test_cleanup_removes_the_probe_tenant_and_nothing_else():
    client = fresh_client()
    put(client, PROBE_TENANT, "sys:a")
    put(client, "kestrel", "sys:a")
    put(client, f"{PROBE_TENANT}-2", "sys:a")  # shares the prefix without the delimiter
    assert delete_probe_items(client) == 1
    left = {i["PK"]["S"] for i in client.scan(TableName=TABLE_NAME)["Items"]}
    assert left == {keys.node_pk("kestrel", "sys:a"), keys.node_pk(f"{PROBE_TENANT}-2", "sys:a")}


@mock_aws
def test_a_failing_test_still_leaves_nothing_behind():
    client = fresh_client()
    try:
        with probe_session(client):
            put(client, PROBE_TENANT, "sys:a")
            raise RuntimeError("the test failed")
    except RuntimeError:
        pass
    assert probe_keys(client) == []
