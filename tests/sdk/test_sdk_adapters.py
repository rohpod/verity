"""The Bedrock and OpenAI adapters against fakes (ADR 0007, ADR 0023). No network, no AWS."""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from verity_ai.bedrock import BedrockCompatible
from verity_ai.errors import AdapterError, RefusedTarget
from verity_ai.openai import OpenAICompatible, urllib_transport

CANARY = "VERITY-CANARY-7f3a"
URL = "https://abc123.lambda-url.eu-north-1.on.aws/v1"
MESSAGES = [{"role": "user", "content": [{"text": CANARY}]}]
CONVERSE = {
    "output": {"message": {"role": "assistant", "content": [{"text": "[SIMULATED] hi"}]}},
    "stopReason": "end_turn",
    "usage": {"inputTokens": 3, "outputTokens": 4, "totalTokens": 7},
    "metrics": {"latencyMs": 1},
}
COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "[SIMULATED]"}}],
    "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
}


def no_sign(method, url, body, headers):
    return headers


def transport_returning(status, body=b""):
    calls = []

    def transport(method, url, data, headers, timeout):
        calls.append((method, url, data, headers, timeout))
        return status, body

    transport.calls = calls
    return transport


def ok_transport():
    return transport_returning(200, json.dumps(COMPLETION).encode())


def test_converse_sends_only_the_given_fields_and_reports_total_tokens():
    seen, tokens = [], []
    adapter = BedrockCompatible(lambda r: seen.append(r) or CONVERSE, usage=tokens.append)
    assert adapter.converse(modelId="mock.bedrock-fm-v1", messages=MESSAGES) == CONVERSE
    assert seen == [{"modelId": "mock.bedrock-fm-v1", "messages": MESSAGES}]
    assert tokens == [7]
    adapter.converse(modelId="m", messages=MESSAGES, system=[{"text": "s"}], inferenceConfig={})
    assert set(seen[1]) == {"modelId", "messages", "system", "inferenceConfig"}


def test_usage_is_a_required_keyword_on_both_adapters():
    with pytest.raises(TypeError):
        BedrockCompatible(lambda r: CONVERSE)
    with pytest.raises(TypeError):
        OpenAICompatible(URL, sign=no_sign)
    BedrockCompatible(lambda r: CONVERSE, usage=None)  # a deliberate choice


def test_a_raising_usage_hook_does_not_fail_the_call_and_logs_only_the_type(caplog):
    def boom(tokens):
        raise RuntimeError(CANARY)

    adapter = BedrockCompatible(lambda r: CONVERSE, usage=boom)
    with caplog.at_level(logging.DEBUG):
        assert adapter.converse(modelId="m", messages=MESSAGES) == CONVERSE
    assert "usage_write_failed RuntimeError" in caplog.text
    assert CANARY not in caplog.text


def test_a_failed_model_call_writes_no_usage():
    tokens = []

    def fail(request):
        raise AdapterError(500)

    with pytest.raises(AdapterError):
        BedrockCompatible(fail, usage=tokens.append).converse(modelId="m", messages=MESSAGES)
    transport = transport_returning(500, CANARY.encode())
    adapter = OpenAICompatible(URL, sign=no_sign, usage=tokens.append, transport=transport)
    with pytest.raises(AdapterError):
        adapter.chat_completions(model="m", messages=[])
    assert tokens == []


def test_chat_completions_posts_signed_json_to_the_completions_path():
    transport = ok_transport()
    tokens = []

    def sign(method, url, body, headers):
        return {**headers, "Authorization": "signed"}

    adapter = OpenAICompatible(URL + "/", sign=sign, usage=tokens.append, transport=transport)
    assert (
        adapter.chat_completions(model="mock-gpt-class", messages=[], temperature=0) == COMPLETION
    )
    method, url, data, headers, timeout = transport.calls[0]
    assert (method, url) == ("POST", URL + "/chat/completions")
    assert json.loads(data) == {"model": "mock-gpt-class", "messages": [], "temperature": 0}
    assert headers["Authorization"] == "signed"
    assert timeout == 5.0
    assert tokens == [5]


def test_an_error_holds_the_status_and_never_the_body():
    transport = transport_returning(403, CANARY.encode())
    adapter = OpenAICompatible(URL, sign=no_sign, usage=None, transport=transport)
    with pytest.raises(AdapterError) as caught:
        adapter.chat_completions(model="m", messages=[])
    assert caught.value.status == 403
    assert CANARY not in str(caught.value)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://abc123.lambda-url.us-east-1.on.aws/v1",
        "https://abc123.lambda-url.eu-north-1.on.aws.evil.example/v1",
        "https://evil.example/#.lambda-url.eu-north-1.on.aws/v1",
        "https://user:pw@abc123.lambda-url.eu-north-1.on.aws/v1",
        "http://abc123.lambda-url.eu-north-1.on.aws/v1",
        "https://.lambda-url.eu-north-1.on.aws/v1",
        "http://localhost.evil.example/v1",
        "https://localhost/v1",
        "https://abc123.lambda-url.eu-north-1.on.aws",
    ],
)
def test_the_openai_adapter_refuses_anything_but_a_mock_endpoint(url):
    with pytest.raises(RefusedTarget):
        OpenAICompatible(url, sign=no_sign, usage=None)


@pytest.mark.parametrize("url", [URL, "http://localhost/v1", "http://localhost:8080/v1/"])
def test_the_openai_adapter_accepts_a_mock_function_url_and_localhost(url):
    OpenAICompatible(url, sign=no_sign, usage=None)


def test_prompts_and_replies_are_never_logged(caplog):
    with caplog.at_level(logging.DEBUG):
        BedrockCompatible(lambda r: CONVERSE, usage=None).converse(modelId="m", messages=MESSAGES)
        adapter = OpenAICompatible(URL, sign=no_sign, usage=None, transport=ok_transport())
        adapter.chat_completions(model="m", messages=MESSAGES)
    assert CANARY not in caplog.text
    assert "[SIMULATED]" not in caplog.text


def test_a_response_with_no_usage_fails_one_way_and_holds_no_body():
    tokens = []
    with pytest.raises(AdapterError) as caught:
        BedrockCompatible(lambda r: {"output": CANARY}, usage=tokens.append).converse(
            modelId="m", messages=MESSAGES
        )
    assert CANARY not in str(caught.value) and caught.value.__cause__ is None
    assert caught.value.__suppress_context__ and tokens == []


@pytest.mark.parametrize(
    "body",
    [
        CANARY.encode(),
        b"",
        json.dumps({"choices": [CANARY]}).encode(),
        json.dumps({"usage": CANARY}).encode(),
        json.dumps([CANARY]).encode(),
    ],
)
def test_an_openai_body_that_is_not_json_or_has_no_usage_is_an_adapter_error(body):
    tokens = []
    adapter = OpenAICompatible(
        URL, sign=no_sign, usage=tokens.append, transport=transport_returning(200, body)
    )
    with pytest.raises(AdapterError) as caught:
        adapter.chat_completions(model="m", messages=[])
    assert caught.value.status == 200 and CANARY not in str(caught.value)
    assert caught.value.__suppress_context__ and tokens == []


class Recorder(BaseHTTPRequestHandler):
    seen: list
    location: str | None = None

    def do_POST(self):
        self.server.seen.append(self.headers.get("Authorization"))
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(302 if self.server.location else 200)
        if self.server.location:
            self.send_header("Location", self.server.location)
        self.end_headers()

    def log_message(self, *args):
        pass


def serve(location=None):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    server.seen, server.location = [], location
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_a_redirect_is_not_followed_and_surfaces_as_its_status():
    target = serve()
    origin = serve(location=f"http://127.0.0.1:{target.server_port}/elsewhere")
    try:
        url = f"http://127.0.0.1:{origin.server_port}/v1/chat/completions"
        assert urllib_transport("POST", url, b"{}", {"Authorization": "signed"}, 2.0) == (302, b"")
        adapter = OpenAICompatible(
            "http://localhost/v1",
            sign=no_sign,
            usage=None,
            transport=lambda m, u, b, h, t: urllib_transport(m, url, b, {"Authorization": "x"}, t),
        )
        with pytest.raises(AdapterError) as caught:
            adapter.chat_completions(model="m", messages=[])
        assert caught.value.status == 302
        assert origin.seen == ["signed", "x"] and target.seen == []
    finally:
        origin.shutdown()
        target.shutdown()


def test_a_refused_connection_and_a_timeout_are_adapter_errors_without_a_status():
    free = serve()
    port = free.server_port
    free.shutdown()
    free.server_close()
    with pytest.raises(AdapterError) as refused:
        urllib_transport("POST", f"http://127.0.0.1:{port}/", b"{}", {}, 1.0)
    assert refused.value.status is None


def test_a_timeout_is_an_adapter_error(monkeypatch):
    def slow(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("verity_ai.openai._opener.open", slow)
    with pytest.raises(AdapterError) as caught:
        urllib_transport("POST", "http://127.0.0.1:1/", b"{}", {}, 0.1)
    assert caught.value.status is None
