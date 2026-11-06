"""The Lambda invoker and the SigV4 signer (ADR 0009, ADR 0023). Fakes and static credentials."""

import io
import json

import pytest
from botocore.credentials import Credentials
from verity_ai.aws import lambda_invoker, sigv4_signer
from verity_ai.errors import AdapterError, RefusedTarget


class FakeLambda:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def reply(body, **extra):
    return {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(body).encode()), **extra}


def test_the_invoker_sends_the_event_as_json_and_parses_the_reply():
    client = FakeLambda(reply({"ok": True}))
    assert lambda_invoker("mock-bedrock", client=client)({"a": 1}) == {"ok": True}
    assert client.calls == [{"FunctionName": "mock-bedrock", "Payload": '{"a": 1}'}]


def test_a_function_error_raises_with_the_status_only():
    client = FakeLambda(reply({"errorMessage": "VERITY-CANARY-7f3a"}, FunctionError="Unhandled"))
    with pytest.raises(AdapterError) as caught:
        lambda_invoker("mock-bedrock", client=client)({})
    assert caught.value.status == 200
    assert "CANARY" not in str(caught.value)


@pytest.mark.parametrize("name", ["support-assistant", "bedrock", "MOCK-bedrock", "my-mock-x", ""])
def test_the_invoker_refuses_any_function_not_named_mock(name):
    with pytest.raises(RefusedTarget):
        lambda_invoker(name, client=FakeLambda(reply({})))


def test_sigv4_signs_for_lambda_with_the_session_token_and_leaves_the_body_alone():
    credentials = Credentials("AKIDEXAMPLE", "secret", token="session-token")
    body = b'{"model": "m"}'
    url = "https://abc123.lambda-url.eu-north-1.on.aws/v1/chat/completions"
    signed = sigv4_signer(credentials=credentials)("POST", url, body, {"Content-Type": "x"})
    assert signed["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
    assert "/eu-north-1/lambda/aws4_request" in signed["Authorization"]
    assert signed["X-Amz-Security-Token"] == "session-token"
    assert signed["Content-Type"] == "x"
    assert body == b'{"model": "m"}'


def test_the_signature_covers_the_body():
    credentials = Credentials("AKIDEXAMPLE", "secret")
    sign = sigv4_signer(credentials=credentials)
    url = "https://abc123.lambda-url.eu-north-1.on.aws/v1/chat/completions"
    first = sign("POST", url, b"one", {})["Authorization"]
    second = sign("POST", url, b"two", {})["Authorization"]
    assert first.split("Signature=")[1] != second.split("Signature=")[1]
