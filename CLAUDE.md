# Verity: project rules for Claude Code

AI governance/risk/compliance platform: a learning and portfolio project built to enterprise standards. Design docs live in `docs/` (read `docs/architecture.md` and `docs/adr/` before changing architecture).

## Hard constraints (never violate)
1. **Zero cost.** The AWS account is on the **Free plan** (credit-based, expires ~6 months after creation). Use only Always Free allowances: Lambda, DynamoDB (provisioned + Standard class, ≤25 RCU/WCU total incl. GSIs, auto-scaling off), EventBridge Scheduler, SSM Parameter Store (standard), CloudTrail *event history*, Resource Explorer (no Config-backed views), CloudWatch Logs ≤5 GB (3-day retention), Budgets without actions.
   - **Never use:** S3, Secrets Manager, API Gateway, Neptune, AWS Config, NAT Gateway, VPC Flow Logs, CloudTrail trails/Lake, Bedrock/SageMaker *invocation*, on-demand DynamoDB, multi-region features, or AWS Organizations.
   - Never suggest upgrading the account to the Paid plan.
   - Before adding any AWS service not listed above, verify its current pricing and Free plan availability on official AWS pages and ask the user.
2. **AWS only**, single region **eu-west-1**. The only exception is GitHub Pages hosting of the static demo snapshot.
3. **Ask before any mutating AWS action** (`terraform/tofu apply|destroy`, `aws ... create|put|delete|update`). Explain what it creates, the verified price, and how to delete it.

## Honesty rules
- Bedrock and OpenAI are **mock-only**. Never claim they were invoked. Label simulated components in code, docs and UI.
- All people, companies and personal data are **fictional/synthetic**. No real PII.
- The crawler reads env var **names only**, never values.
- Public snapshots must redact the AWS account ID and function URLs.

## Content rules
- **ISO 42001/27001:** reference clause/control IDs with **original summaries only**. Never reproduce ISO text.
- EU AI Act: Regulation (EU) 2024/1689 **as amended by (EU) 2026/1744**. Obligation dates are data with `source_url` + `last_verified`, never hard-coded.
- Crosswalk uses NIST IR 8477 STRM relationship types via the hub control library; never treat similar controls as equal without rationale.
- Automated checks may only raise `automatable: true` controls; organisational/legal controls need human (L4) verification to be fully implemented.

## Stack & conventions
- Python 3.12 via `uv`, pydantic v2, NetworkX, pytest (with `moto` for AWS), ruff. Lambdas: arm64, small zips, no heavy deps (pure-Python ML inference).
- Terraform/OpenTofu in `infra/`, local state (never committed). Direct Lambda zip upload (no S3).
- Frontend: Vite + React + TS, shadcn/ui + Tailwind, reads `snapshot.json` only.
- All graph access goes through the `GraphRepository` interface. Never call DynamoDB directly from features.
- Record significant decisions as a new ADR in `docs/adr/`.

## Working style
Work in stages, explain unfamiliar concepts briefly, challenge weak assumptions, and don't dump large implementations at once.
