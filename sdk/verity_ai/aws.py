"""The Lambda invoker and the SigV4 signer: the only `verity_ai` module that imports boto3.

The adapters take these as injected callables, so app code never imports boto3. It is the third
file allowed to (ADR 0023, decision 2); `tests/graph/test_boto3_boundary.py` enforces that.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from botocore.session import Session

from verity_ai.errors import AdapterError, RefusedTarget

REGION = "eu-north-1"  # the only region Verity uses (ADR 0011)
MOCK_PREFIX = "mock-"
# At DEBUG these log request bodies and the session token, whatever the root logger's level.
QUIET_LOGGERS = ("botocore", "boto3", "urllib3")


def _quiet() -> None:
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def lambda_invoker(function_name: str, *, client: Any = None) -> Callable[[dict], dict]:
    """Invokes a mock function with a JSON event. Refuses any name not starting `mock-`."""
    if not function_name.startswith(MOCK_PREFIX):
        raise RefusedTarget("only functions named mock-* can be invoked")
    _quiet()
    if client is None:
        # One attempt: a retried model call would be counted twice.
        config = Config(retries={"total_max_attempts": 1}, connect_timeout=0.5, read_timeout=5)
        client = boto3.client("lambda", region_name=REGION, config=config)
    lambda_client = client

    def invoke(event: dict) -> dict:
        try:
            response = lambda_client.invoke(FunctionName=function_name, Payload=json.dumps(event))
        except (ClientError, BotoCoreError):  # a timeout is a BotoCoreError
            raise AdapterError(None) from None
        if response.get("FunctionError"):
            raise AdapterError(response["StatusCode"])
        return json.loads(response["Payload"].read())

    return invoke


def sigv4_signer(region: str = REGION, *, credentials: Any = None):
    """Signs the exact body bytes that are sent, for a Function URL (service name `lambda`).
    Credentials come from the session unless given."""
    _quiet()

    def sign(method: str, url: str, body: bytes, headers: dict) -> dict:
        _quiet()
        creds = credentials if credentials is not None else Session().get_credentials()
        request = AWSRequest(method=method, url=url, data=body, headers=dict(headers))
        SigV4Auth(creds.get_frozen_credentials(), "lambda", region).add_auth(request)
        return dict(request.headers)

    return sign
