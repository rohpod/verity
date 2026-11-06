"""SIMULATED Amazon Bedrock. Nothing here calls Bedrock (ADR 0007, ADR 0023).

Takes a Converse request as the event and returns a Converse response. The reply is a template
over the input and tokens are `ceil(len(text) / 4)`, so every answer is deterministic. It checks
no auth and logs no content: on AWS the caller needs `lambda:InvokeFunction`. Bad input raises,
so the invoke comes back with a `FunctionError`.
"""

import math

MODEL_ID = "mock.bedrock-fm-v1"  # invented, never a real model ID


def _tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def _texts(blocks) -> list[str]:
    return [block["text"] for block in blocks if "text" in block]


def converse(event: dict) -> dict:
    model_id, messages = event["modelId"], event["messages"]
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("modelId must be a non-empty string")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list")
    prompt: list[str] = _texts(event.get("system") or [])
    last_user = ""
    for message in messages:
        if message["role"] not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")
        texts = _texts(message["content"])
        prompt += texts
        if message["role"] == "user":
            last_user = " ".join(texts)
    reply = f"[SIMULATED] Mock reply to {len(messages)} message(s). You wrote: {last_user[:200]}"
    input_tokens = _tokens(" ".join(prompt))
    output_tokens = _tokens(reply)
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": reply}]}},
        "stopReason": "end_turn",
        "usage": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
        },
        "metrics": {"latencyMs": 0},
        "additionalModelResponseFields": {"simulated": True},
    }


def handler(event, context):
    return converse(event)
