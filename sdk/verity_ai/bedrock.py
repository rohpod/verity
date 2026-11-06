"""`BedrockCompatible`: the Converse request and response shape, sent to `mock-bedrock`.

SIMULATED. Nothing here calls Bedrock. It takes an injected `invoke` callable, which is
`aws.lambda_invoker("mock-bedrock")` on AWS and a local function in tests.
"""

from collections.abc import Callable

from verity_ai.errors import AdapterError
from verity_ai.hook import UsageHook, notify


class BedrockCompatible:
    def __init__(self, invoke: Callable[[dict], dict], *, usage: UsageHook | None):
        """`usage` has no default: passing `None` is a choice to write no telemetry."""
        self._invoke = invoke
        self._usage = usage

    def converse(self, *, modelId, messages, system=None, inferenceConfig=None) -> dict:
        request: dict = {"modelId": modelId, "messages": messages}
        if system is not None:
            request["system"] = system
        if inferenceConfig is not None:
            request["inferenceConfig"] = inferenceConfig
        response = self._invoke(request)
        try:
            tokens = response["usage"]["totalTokens"]
        except (KeyError, TypeError):
            raise AdapterError(None) from None  # the response may hold personal data
        notify(self._usage, tokens)
        return response
