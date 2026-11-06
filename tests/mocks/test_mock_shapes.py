"""The mocks keep the provider shapes and label themselves simulated (ADR 0007, ADR 0023)."""

import base64
import json

import pytest
from botocore.loaders import Loader
from botocore.model import ServiceModel
from botocore.validate import ParamValidator
from estate_support import load_app

bedrock = load_app("mocks/mock_bedrock")
openai = load_app("mocks/mock_openai")

# The schema is a JSON file. This validates against it and creates no client.
CONVERSE = ServiceModel(
    Loader().load_service_model("bedrock-runtime", "service-2")
).operation_model("Converse")
REQUEST = {
    "modelId": "mock.bedrock-fm-v1",
    "messages": [{"role": "user", "content": [{"text": "How do I reset my password?"}]}],
    "system": [{"text": "You are a Kestrel Cloud help assistant."}],
    "inferenceConfig": {"maxTokens": 256, "temperature": 0.0},
}


def issues(shape, value) -> list:
    return ParamValidator().validate(value, shape).generate_report().splitlines()


def completions_event(body, *, method="POST", path="/v1/chat/completions", encoded=False):
    raw = body if isinstance(body, str) else json.dumps(body)
    if encoded:
        raw = base64.b64encode(raw.encode()).decode()
    return {
        "requestContext": {"http": {"method": method, "path": path}},
        "body": raw,
        "isBase64Encoded": encoded,
    }


def test_bedrock_request_and_response_are_valid_converse_shapes():
    assert issues(CONVERSE.input_shape, REQUEST) == []
    response = bedrock.handler(REQUEST, None)
    assert issues(CONVERSE.output_shape, response) == []


def test_the_converse_schema_check_has_teeth():
    assert issues(CONVERSE.output_shape, {**bedrock.handler(REQUEST, None), "simulated": True})


def test_bedrock_is_deterministic_and_counts_tokens():
    first, second = bedrock.handler(REQUEST, None), bedrock.handler(REQUEST, None)
    assert first == second
    usage = first["usage"]
    assert usage["totalTokens"] == usage["inputTokens"] + usage["outputTokens"] > 0
    assert first["stopReason"] == "end_turn"


def test_bedrock_labels_the_response_simulated_inside_the_valid_shape():
    response = bedrock.handler(REQUEST, None)
    assert response["additionalModelResponseFields"] == {"simulated": True}
    assert response["output"]["message"]["content"][0]["text"].startswith("[SIMULATED]")
    assert bedrock.MODEL_ID == "mock.bedrock-fm-v1"


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"modelId": "", "messages": REQUEST["messages"]},
        {"modelId": "m", "messages": []},
        {"modelId": "m", "messages": [{"role": "system", "content": []}]},
    ],
)
def test_bedrock_raises_on_bad_input_so_the_invoke_reports_a_function_error(event):
    with pytest.raises((ValueError, KeyError)):
        bedrock.handler(event, None)


COMPLETION_REQUEST = {
    "model": "mock-gpt-class",
    "messages": [{"role": "user", "content": "Summarise this Kestrel Cloud contract."}],
}


def test_openai_returns_the_chat_completion_shape_and_labels():
    # The shape is from knowledge: the API reference returned 403 to automated fetches (ADR 0023).
    response = openai.handler(completions_event(COMPLETION_REQUEST), None)
    assert response["statusCode"] == 200
    assert response["headers"]["x-verity-simulated"] == "true"
    body = json.loads(response["body"])
    assert set(body) == {
        "id",
        "object",
        "created",
        "model",
        "choices",
        "usage",
        "system_fingerprint",
    }
    assert body["object"] == "chat.completion"
    assert body["system_fingerprint"] == "verity-mock"
    [choice] = body["choices"]
    assert set(choice) == {"index", "message", "finish_reason"}
    assert set(choice["message"]) == {"role", "content"}
    assert choice["message"]["content"].startswith("[SIMULATED]")
    usage = body["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_openai_is_deterministic_and_decodes_base64_bodies():
    plain = openai.handler(completions_event(COMPLETION_REQUEST), None)
    assert plain == openai.handler(completions_event(COMPLETION_REQUEST), None)
    assert plain == openai.handler(completions_event(COMPLETION_REQUEST, encoded=True), None)


def test_openai_accepts_content_parts():
    request = {
        "model": "m",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "x"}]}],
    }
    assert openai.handler(completions_event(request), None)["statusCode"] == 200


@pytest.mark.parametrize(
    ("event", "status"),
    [
        (completions_event(COMPLETION_REQUEST, path="/v1/models"), 404),
        (completions_event(COMPLETION_REQUEST, method="GET"), 405),
        (completions_event("not json"), 400),
        (completions_event({"model": "m"}), 400),
        (completions_event({"messages": []}), 400),
        (completions_event({"messages": [{"role": "user"}]}), 400),
        (completions_event("[1]"), 400),
    ],
)
def test_openai_errors_use_the_error_object(event, status):
    response = openai.handler(event, None)
    assert response["statusCode"] == status
    error = json.loads(response["body"])["error"]
    assert set(error) == {"message", "type", "param", "code"}


def test_every_mock_docstring_starts_simulated():
    assert bedrock.__doc__.startswith("SIMULATED")
    assert openai.__doc__.startswith("SIMULATED")
