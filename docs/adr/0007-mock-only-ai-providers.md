# 0007 — Bedrock and OpenAI are mock-only, behind an adapter SDK
- **Status:** Accepted (2026-11-05)

## Context
Bedrock is available on the Free plan but would be paid from credits. The owner chose strict zero paid inference. OpenAI is a paid, non-AWS service.

## Decision
`sdk/verity_ai` defines provider adapters:
- `BedrockCompatible`, which mimics the Converse request and response shape and invokes the `mock-bedrock` Lambda over IAM;
- `OpenAICompatible`, which takes a base URL and key and calls the `mock-openai` Function URL's `/v1/chat/completions`.

The adapters also write usage telemetry. **Bedrock is never invoked.** The support assistant's role intentionally holds an unused `bedrock:Converse` grant. This demonstrates the crawler's "capability without usage" least-privilege finding.

## Consequences
- Every simulated component is labelled in code, docs and UI (`Provider.simulated = true`).
- Swapping in a real provider later means changing configuration, not code.
- CloudTrail will honestly show no Bedrock activity.
