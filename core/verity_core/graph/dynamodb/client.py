"""The boto3 client, configured once. One of the few modules allowed to import boto3."""

from typing import Any

import boto3
from botocore.config import Config

REGION = "eu-north-1"  # the only region Verity uses (ADR 0011)


def default_client() -> Any:
    """A DynamoDB client that retries throttled calls with exponential backoff (D14). boto3's
    default is the older `legacy` mode, so the retry mode is set explicitly. `total_max_attempts`
    counts the first try, unlike `max_attempts`, which counts only the retries."""
    config = Config(retries={"mode": "standard", "total_max_attempts": 10})
    return boto3.client("dynamodb", region_name=REGION, config=config)
