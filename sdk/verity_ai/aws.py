"""The Lambda invoker and the SigV4 signer: the only `verity_ai` module that imports boto3.

The adapters take these as injected callables, so app code never imports boto3. It is the third
file allowed to (ADR 0023, decision 2); `tests/graph/test_boto3_boundary.py` enforces that.
"""

import json
from collections.abc import Callable
from typing import Any

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.session import Session

from verity_ai.errors import AdapterError, RefusedTarget

REGION = "eu-north-1"  # the only region Verity uses (ADR 0011)
MOCK_PREFIX = "mock-"


def lambda_invoker(function_name: str, *, client: Any = None) -> Callable[[dict], dict]:
    """Invokes a mock function with a JSON event. Refuses any name not starting `mock-`."""
    if not function_name.startswith(MOCK_PREFIX):
        raise RefusedTarget("only functions named mock-* can be invoked")
    lambda_client = client if client is not None else boto3.client("lambda", region_name=REGION)

    def invoke(event: dict) -> dict:
        response = lambda_client.invoke(FunctionName=function_name, Payload=json.dumps(event))
        if response.get("FunctionError"):
            raise AdapterError(response["StatusCode"])
        return json.loads(response["Payload"].read())

    return invoke


def sigv4_signer(region: str = REGION, *, credentials: Any = None):
    """Signs the exact body bytes that are sent, for a Function URL (service name `lambda`).
    Credentials come from the session unless given."""

    def sign(method: str, url: str, body: bytes, headers: dict) -> dict:
        creds = credentials if credentials is not None else Session().get_credentials()
        request = AWSRequest(method=method, url=url, data=body, headers=dict(headers))
        SigV4Auth(creds.get_frozen_credentials(), "lambda", region).add_auth(request)
        return dict(request.headers)

    return sign
