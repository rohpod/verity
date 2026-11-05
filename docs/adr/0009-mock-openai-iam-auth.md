# 0009 — mock-openai uses an AWS_IAM Function URL; reserved concurrency is dropped
- **Status:** Accepted (2026-11-05). Amends [0007](0007-mock-only-ai-providers.md); 0007 otherwise stays in force.

## Context
Architecture §J planned a public `NONE`-auth Function URL for mock-openai, protected by a bearer key in SSM and a reserved concurrency of 1. A read-only check of the account (2026-11-05) showed the Lambda account concurrency limit is **10**. Lambda requires 100 units to stay unreserved ([concurrency docs](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html)), so reserved concurrency cannot be set at all. A public endpoint would then have no brake, and a flood could invoke the function repeatedly and burn credits.

## Decision
- mock-openai's Function URL uses `AWS_IAM` auth. Nothing is public, and unsigned requests never run the function.
- The `OpenAICompatible` adapter gets a SigV4 signing hook. The OpenAI-shaped request and response (`/v1/chat/completions`) are unchanged.
- The SSM bearer key is removed.
- Reserved concurrency is dropped from all guardrail lists. The remaining guardrails are the budget alert, 3-day log retention and Always Free sizing.

## Alternatives
- Keep `NONE` plus a bearer key: closest to a real OpenAI client, but it is a public endpoint with no brake.
- Request a quota increase: a mutating request with an unknown outcome on the Free plan, and the limit would have to exceed 100.

## Consequences
- The mock is less drop-in for third-party OpenAI clients. That is acceptable, since only our own adapter calls it.
- The Function URL's price is not yet confirmed on an official page. It is verified before M8 (see [Stage 4](../stage-4-milestones.md)).
