"""Provider adapters for the demo estate (ADR 0007, ADR 0023).

Bedrock and OpenAI are mock-only: the adapters only reach `mock-bedrock` and `mock-openai`.
This package imports nothing heavy, so a function pays only for the modules it uses:
`bedrock` and `openai` are stdlib only, `telemetry` is the one that needs `verity_core`, and
`aws` is the one that needs boto3.
"""
