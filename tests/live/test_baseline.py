"""Read-only checks of the real account against what M3 requires (ADR 0015)."""

import boto3
from live_support import live_only
from verity_core.graph.dynamodb.client import REGION
from verity_core.graph.dynamodb.table import TABLE_NAME, table_definition

pytestmark = live_only

# One concrete action for each entry in infra/bootstrap/verity-never-use.json.
NEVER_USE = [
    "apigateway:POST",
    "bedrock:InvokeModel",
    "cloudtrail:CreateEventDataStore",
    "cloudtrail:CreateTrail",
    "config:PutConfigurationRecorder",
    "ec2:CreateFlowLogs",
    "ec2:CreateNatGateway",
    "freetier:UpgradeAccountPlan",
    "neptune-graph:CreateGraph",
    "organizations:CreateAccount",
    "organizations:CreateOrganization",
    "rds:CreateDBCluster",
    "rds:CreateDBInstance",
    "s3:CreateBucket",
    "sagemaker:InvokeEndpoint",
    "secretsmanager:CreateSecret",
]


def dynamodb():
    return boto3.client("dynamodb", region_name=REGION)


def test_the_real_table_matches_its_single_description():
    table = dynamodb().describe_table(TableName=TABLE_NAME)["Table"]
    wanted = table_definition()
    assert table["TableStatus"] == "ACTIVE"
    assert table["KeySchema"] == wanted["KeySchema"]
    capacity = table["ProvisionedThroughput"]
    assert capacity["ReadCapacityUnits"] == wanted["ProvisionedThroughput"]["ReadCapacityUnits"]
    assert capacity["WriteCapacityUnits"] == wanted["ProvisionedThroughput"]["WriteCapacityUnits"]
    (index,) = table["GlobalSecondaryIndexes"]
    (wanted_index,) = wanted["GlobalSecondaryIndexes"]
    assert index["IndexName"] == wanted_index["IndexName"]
    assert index["Projection"] == wanted_index["Projection"]
    for name, value in wanted_index["ProvisionedThroughput"].items():
        assert index["ProvisionedThroughput"][name] == value


def test_the_table_is_provisioned_and_standard():
    table = dynamodb().describe_table(TableName=TABLE_NAME)["Table"]
    # AWS leaves both summaries out for a default table, as seen on this one. The console
    # showed "DynamoDB Standard". A value here must still be the free combination.
    assert table.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED") == "PROVISIONED"
    assert table.get("TableClassSummary", {}).get("TableClass", "STANDARD") == "STANDARD"


def test_nothing_that_could_cost_money_is_switched_on():
    client = dynamodb()
    table = client.describe_table(TableName=TABLE_NAME)["Table"]
    assert "StreamSpecification" not in table
    backups = client.describe_continuous_backups(TableName=TABLE_NAME)
    recovery = backups["ContinuousBackupsDescription"]["PointInTimeRecoveryDescription"]
    assert recovery["PointInTimeRecoveryStatus"] == "DISABLED"
    scaling = boto3.client("application-autoscaling", region_name=REGION)
    assert scaling.describe_scalable_targets(ServiceNamespace="dynamodb")["ScalableTargets"] == []


def test_aws_denies_every_never_use_action_and_allows_the_table():
    arn = boto3.client("sts").get_caller_identity()["Arn"]
    iam = boto3.client("iam")

    def decisions(actions):
        found = iam.simulate_principal_policy(PolicySourceArn=arn, ActionNames=actions)
        return {r["EvalActionName"]: r["EvalDecision"] for r in found["EvaluationResults"]}

    assert set(decisions(NEVER_USE).values()) == {"explicitDeny"}
    assert decisions(["dynamodb:PutItem"]) == {"dynamodb:PutItem": "allowed"}
