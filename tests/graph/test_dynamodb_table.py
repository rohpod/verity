import boto3
import pytest
from moto import mock_aws
from verity_core.graph.dynamodb.table import (
    FREE_ALLOWANCE_UNITS,
    GSI_RCU,
    GSI_WCU,
    TABLE_NAME,
    TABLE_RCU,
    TABLE_WCU,
    table_definition,
)

REGION = "eu-north-1"  # the only region Verity uses (ADR 0011)


def test_capacity_stays_inside_the_always_free_allowance():
    assert TABLE_RCU + GSI_RCU <= FREE_ALLOWANCE_UNITS
    assert TABLE_WCU + GSI_WCU <= FREE_ALLOWANCE_UNITS
    assert (TABLE_RCU, TABLE_WCU, GSI_RCU, GSI_WCU) == (15, 15, 10, 10)


def test_the_definition_is_provisioned_and_standard_never_on_demand():
    definition = table_definition()
    assert definition["TableName"] == TABLE_NAME == "verity-graph"
    assert definition["BillingMode"] == "PROVISIONED"
    assert definition["TableClass"] == "STANDARD"
    assert "PAY_PER_REQUEST" not in str(definition)


def test_the_gsi_projects_keys_only():
    (gsi,) = table_definition()["GlobalSecondaryIndexes"]
    assert gsi["IndexName"] == "GSI1" and gsi["Projection"] == {"ProjectionType": "KEYS_ONLY"}
    assert gsi["ProvisionedThroughput"] == {"ReadCapacityUnits": 10, "WriteCapacityUnits": 10}


def test_every_key_attribute_is_declared_and_nothing_else():
    definition = table_definition()
    declared = {a["AttributeName"] for a in definition["AttributeDefinitions"]}
    used = {k["AttributeName"] for k in definition["KeySchema"]}
    used |= {
        k["AttributeName"] for g in definition["GlobalSecondaryIndexes"] for k in g["KeySchema"]
    }
    assert declared == used == {"PK", "SK", "GSI1PK", "GSI1SK"}


@mock_aws
def test_the_table_can_be_created_and_has_the_expected_shape():
    client = boto3.client("dynamodb", region_name=REGION)
    client.create_table(**table_definition())
    described = client.describe_table(TableName=TABLE_NAME)["Table"]
    assert described["ProvisionedThroughput"]["ReadCapacityUnits"] == TABLE_RCU
    assert described["ProvisionedThroughput"]["WriteCapacityUnits"] == TABLE_WCU
    # moto ignores `TableClass`: it accepts any value and never reports one. The class is pinned
    # by the definition tests above, and M3's real round trip is what checks it on AWS.
    assert "TableClassSummary" not in described
    assert described["BillingModeSummary"]["BillingMode"] == "PROVISIONED"
    (gsi,) = described["GlobalSecondaryIndexes"]
    assert gsi["Projection"]["ProjectionType"] == "KEYS_ONLY"
    assert gsi["ProvisionedThroughput"]["WriteCapacityUnits"] == GSI_WCU


@mock_aws
def test_a_table_name_can_be_chosen_for_tests():
    client = boto3.client("dynamodb", region_name=REGION)
    client.create_table(**table_definition("verity-graph-test"))
    assert client.list_tables()["TableNames"] == ["verity-graph-test"]


@pytest.mark.parametrize("field", ["ProvisionedThroughput", "GlobalSecondaryIndexes"])
def test_the_definition_is_a_fresh_copy_each_time(field):
    first = table_definition()
    first[field] = None
    assert table_definition()[field] is not None
