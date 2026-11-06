"""The boto3 client, configured once. One of the few modules allowed to import boto3."""

from typing import Any

import boto3
from botocore.config import Config

REGION = "eu-north-1"  # the only region Verity uses (ADR 0011)

# The longest a usage write may hold a handler: 2 attempts of 0.5 s to connect and 1 s to read,
# plus one backoff. A test pins the model's timeout plus this against the functions' (ADR 0024).
USAGE_BUDGET_SECONDS = 4


def default_client() -> Any:
    """A DynamoDB client that retries throttled calls with exponential backoff (D14). boto3's
    default is the older `legacy` mode, so the retry mode is set explicitly. `total_max_attempts`
    counts the first try, unlike `max_attempts`, which counts only the retries."""
    config = Config(retries={"mode": "standard", "total_max_attempts": 10})
    return boto3.client("dynamodb", region_name=REGION, config=config)


def usage_client() -> Any:
    """A DynamoDB client for usage telemetry, which must never hold up the call it measures
    (ADR 0023, decision 7). It gives up within `USAGE_BUDGET_SECONDS`, unlike the graph client."""
    config = Config(
        retries={"mode": "standard", "total_max_attempts": 2},
        connect_timeout=0.5,
        read_timeout=1,
    )
    return boto3.client("dynamodb", region_name=REGION, config=config)
