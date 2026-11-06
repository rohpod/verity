"""Shadow Summariser: summarises text for one team. A shadow-AI example, on purpose.

A team wired up the OpenAI-shaped client and never registered the system, so it passes
`usage=None` and writes no usage records. It has no tags, no manifest and no `verity_core` in its
zip, which is how the crawler is meant to find it (architecture section C). The model is
SIMULATED: it calls `mock-openai`, never OpenAI (ADR 0007, ADR 0023). Text is never logged.
"""

import functools
import os

MODEL = "mock-gpt-class"


def run(event: dict, model) -> dict:
    text = event["text"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    response = model.chat_completions(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Summarise this text in two sentences."},
            {"role": "user", "content": text},
        ],
    )
    return {"summary": response["choices"][0]["message"]["content"], "simulated": True}


@functools.cache
def _model():
    from verity_ai.aws import sigv4_signer
    from verity_ai.openai import OpenAICompatible

    return OpenAICompatible(os.environ["OPENAI_BASE_URL"], sign=sigv4_signer(), usage=None)


def handler(event, context):
    return run(event, _model())
