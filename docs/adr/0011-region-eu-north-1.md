# 0011 — Single region is eu-north-1 (Stockholm)
- **Status:** Accepted (2026-11-05). Supersedes the region choice in [0001](0001-free-plan-single-region.md); the rest of 0001 stays in force.

## Context
ADR 0001 chose `eu-west-1`. The owner has since decided to use `eu-north-1`, which is already the AWS CLI's default region. No project resources exist yet, so nothing needs migrating.

## Decision
All Verity resources live in the single region **eu-north-1 (Stockholm)**.

## Alternatives
Keep `eu-west-1`. It offers no benefit to this project, because the design depends on neither region's specific features.

## Consequences
- The EU-exposed customer story and the data-residency attribute still hold, since Stockholm is an EU region.
- Always Free allowances are not tied to this choice. The DynamoDB allowance applies per Region.
- The Stage 4 read-only findings were taken against `eu-west-1`, and Lambda quotas are per Region. Before any apply in M3, re-check that eu-north-1 has no existing Lambda functions or DynamoDB tables, and re-check its Lambda concurrency limit.
- Service endpoints for Lambda, DynamoDB, EventBridge Scheduler, SSM, Resource Explorer and CloudTrail all responded in eu-north-1 on 2026-11-05. Those calls were denied by IAM, so this shows the endpoints exist, not that the services were exercised.
