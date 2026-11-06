"""Contract Insights: summarises customer contracts for sales and legal.

The model is SIMULATED: it calls `mock-openai` through `OpenAICompatible`, never OpenAI
(ADR 0007). Usage records are written for each model call. Contract text is confidential and is
never logged. It is fictional in this demo.
"""

import functools
import logging
import os
from datetime import UTC, datetime

SYSTEM_ID = "sys:contract-insights"
TENANT = "kestrel"
MODEL = "mock-gpt-class"


def run(event: dict, model) -> dict:
    text = event["contract_text"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("contract_text must be a non-empty string")
    response = model.chat_completions(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Summarise this Kestrel Cloud contract in plain words."},
            {"role": "user", "content": text},
        ],
        temperature=0,
    )
    return {
        "summary": response["choices"][0]["message"]["content"],
        "simulated": True,
    }


@functools.cache
def _model():
    from verity_ai.aws import sigv4_signer
    from verity_ai.openai import OpenAICompatible
    from verity_ai.telemetry import UsageRecorder
    from verity_core.graph.dynamodb.usage import DynamoDBUsageSink

    logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    usage = UsageRecorder(
        DynamoDBUsageSink(TENANT, table_name=os.environ["USAGE_TABLE"]),
        tenant=TENANT,
        system_id=SYSTEM_ID,
        provider_id="prov:mock-openai",
        model_id="model:gpt-class",
        clock=lambda: datetime.now(UTC),
    )
    return OpenAICompatible(os.environ["OPENAI_BASE_URL"], sign=sigv4_signer(), usage=usage)


def handler(event, context):
    return run(event, _model())
