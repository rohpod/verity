"""Support Assistant: answers Kestrel Cloud customer questions from bundled help articles.

The model is SIMULATED: it calls `mock-bedrock` through `BedrockCompatible`, never Bedrock
(ADR 0007). It tells the customer they are talking to an AI (Art. 50(1) transparency) and hands
off to a person when no article matches. Usage records are written for each model call. The
customer's message is never logged.
"""

import functools
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

SYSTEM_ID = "sys:support-assistant"
TENANT = "kestrel"
MODEL = "mock.bedrock-fm-v1"
DISCLOSURE = "You are chatting with an AI assistant, not a person. Ask for a human at any time."


def match(articles: list[dict], message: str) -> dict | None:
    """The article with the most keyword hits. Ties go to the first by ID."""
    words = set(re.findall(r"[a-z0-9]+", message.lower()))
    scored = [(len(words & set(a["keywords"])), a["id"], a) for a in articles]
    scored = [entry for entry in scored if entry[0]]
    if not scored:
        return None
    return min(scored, key=lambda entry: (-entry[0], entry[1]))[2]


def run(event: dict, articles: list[dict], model) -> dict:
    message = event["message"]
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be a non-empty string")
    article = match(articles, message)
    context = article["text"] if article else "No help article matches this question."
    response = model.converse(
        modelId=MODEL,
        system=[{"text": f"You are the Kestrel Cloud help assistant. Use only this: {context}"}],
        messages=[{"role": "user", "content": [{"text": message}]}],
        inferenceConfig={"maxTokens": 256, "temperature": 0.0},
    )
    return {
        "reply": response["output"]["message"]["content"][0]["text"],
        "disclosure": DISCLOSURE,
        "handoff": article is None,
        "article_id": article["id"] if article else None,
    }


@functools.cache
def _dependencies():
    from verity_ai.aws import lambda_invoker
    from verity_ai.bedrock import BedrockCompatible
    from verity_ai.telemetry import UsageRecorder
    from verity_core.graph.dynamodb.usage import DynamoDBUsageSink

    logging.getLogger("verity_ai").setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    sink = DynamoDBUsageSink(TENANT, table_name=os.environ["USAGE_TABLE"])
    usage = UsageRecorder(
        sink,
        tenant=TENANT,
        system_id=SYSTEM_ID,
        provider_id="prov:mock-bedrock",
        model_id="model:bedrock-fm",
        clock=lambda: datetime.now(UTC),
    )
    model = BedrockCompatible(lambda_invoker(os.environ["MODEL_ADAPTER"]), usage=usage)
    articles = json.loads((Path(__file__).parent / os.environ["HELP_ARTICLES_FILE"]).read_text())
    return articles, model


def handler(event, context):
    articles, model = _dependencies()
    return run(event, articles, model)
