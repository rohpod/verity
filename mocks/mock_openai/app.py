"""SIMULATED OpenAI. Nothing here calls OpenAI (ADR 0007, ADR 0023).

A Function URL handler (payload format 2.0) for `POST /v1/chat/completions` only. The reply is a
template over the input and tokens are `ceil(len(text) / 4)`, so every answer is deterministic.
It checks no auth and logs no content: on AWS the `AWS_IAM` Function URL refuses unsigned calls
before this code runs (ADR 0009), so that check belongs to M8 and is not faked here.
"""

import base64
import hashlib
import json
import math

HEADERS = {"content-type": "application/json", "x-verity-simulated": "true"}


def _tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def _response(status: int, body: dict) -> dict:
    return {"statusCode": status, "headers": HEADERS, "body": json.dumps(body)}


def _error(status: int, message: str, kind: str, param=None, code=None) -> dict:
    error = {"message": message, "type": kind, "param": param, "code": code}
    return _response(status, {"error": error})


class BadRequest(ValueError):
    """The request cannot be answered. `param` names the field, never its value."""

    def __init__(self, param: str):
        super().__init__(param)
        self.param = param


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(part["text"] for part in content if part.get("type") == "text")


def complete(request: dict) -> dict:
    model = request.get("model")
    if not isinstance(model, str) or not model:
        raise BadRequest("model")
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        raise BadRequest("messages")
    texts = [_text(message["content"]) for message in messages]
    last_user = next(
        (
            t
            for m, t in zip(reversed(messages), reversed(texts), strict=True)
            if m["role"] == "user"
        ),
        "",
    )
    reply = (
        f"[SIMULATED] Mock summary of {len(messages)} message(s). Input began: {last_user[:200]}"
    )
    prompt_tokens = _tokens(" ".join(texts))
    completion_tokens = _tokens(reply)
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    return {
        "id": f"chatcmpl-{digest[:16]}",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "system_fingerprint": "verity-mock",
    }


def handler(event, context):
    http = event["requestContext"]["http"]
    if http["path"] != "/v1/chat/completions":
        return _error(404, "Unknown request URL", "invalid_request_error", code="unknown_url")
    if http["method"] != "POST":
        return _error(405, "Method not allowed", "invalid_request_error", code="method_not_allowed")
    try:
        body = event.get("body") or ""
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode()
        request = json.loads(body)
        if not isinstance(request, dict):
            raise BadRequest("body")
        return _response(200, complete(request))
    except BadRequest as bad:
        return _error(400, "Invalid request body", "invalid_request_error", param=bad.param)
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return _error(400, "Invalid request body", "invalid_request_error", param="messages")
