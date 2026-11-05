# 0015 — Account baseline: identity, credentials and the cost alarm
- **Status:** Accepted (2026-11-05). Builds on [0001](0001-free-plan-single-region.md), [0002](0002-terraform-no-s3.md) and [0011](0011-region-eu-north-1.md); all stay in force.

## Context
M3 is the first milestone that changes the real account. The CLI user `rohpod` has no permissions, and only root can make the first grant. Claude Code's shell runs with the same credentials as the owner, and the project hook guards only that tool. Facts checked on 2026-11-05:
- Budgets without actions are free. `IncludeCredit` defaults to `true`, and AWS's page does not say how that affects an alert.
- The Cost Explorer API costs $0.01 per request, and the `aws ce` reads look read-only.
- IAM is at no additional charge, per its FAQ, which does not name MFA.
- The `freetier` API's page states no price.
- boto3 fails on `aws login` credentials without `botocore[crt]`. No AWS page says whether OpenTofu reads them.

## Decision
**Identity**
- **IAM identities are not managed by OpenTofu.** The owner grants them by hand from root, following `docs/runbooks/m3-account-baseline.md`. The identity running `tofu` should not manage itself, and the first grant has to happen before OpenTofu can run.
- **`rohpod` gets `AdministratorAccess` plus the inline policy `verity-never-use`.** The policy lives in `infra/bootstrap/` and explicitly denies what CLAUDE.md forbids, including S3 bucket creation, Bedrock and SageMaker invocation, and upgrading the plan. It covers M3 and M8 without further grants from root.
- **The deny policy stops accidents, not intent.** An admin can remove it. It cannot express "no on-demand DynamoDB", which the `infra/` tests cover.

**Credentials**
- **A local `verity` profile uses `credential_process`,** which AWS documents for tools that cannot read `aws login` sessions. It serves boto3 and OpenTofu alike, adds no dependency to the repo and needs no long-lived access key.

**Cost guardrails**
- **The budget excludes credits and has no actions.** A $0.01 monthly COST budget with `include_credit = false`, so usage that credits pay for is not hidden. We cannot test that the alert fires without spending money.
- **The owner reads credits in the Billing console,** before and after any live work. That is the check we can rely on. Claude does not call `aws ce`, and the hook always asks if it tries.
- **Tests keep `infra/` free.** CI parses the HCL, compares it with `table_definition()`, limits capacity to 25/25 and limits resources to an approved list.
- **Live tests need `VERITY_LIVE_AWS=1`.** They write through boto3, which the hook cannot see, so the hook asks when that switch appears.

## Alternatives
| Option | Why not chosen |
|---|---|
| `AdministratorAccess` alone | The hard constraints would rest on one tool's hook and on review |
| A scoped policy for `rohpod` | Least privilege, but M8 would need root grants for Lambda, IAM roles and Scheduler each time |
| `rohpod` managed in OpenTofu | Needs admin access before it can grant admin access, and a bad apply could lock the operator out |
| Access keys for OpenTofu | Long-lived secrets on disk, which `aws login` exists to avoid |
| Adding `botocore[crt]` | Fixes boto3 only, and adds a native dependency for a local concern |
| Keeping the budget's default credit setting | Credits could hide the usage the alarm exists to report |

## Consequences
- Budgets and the `freetier` API are global billing services, not resources in a second region, so ADR 0011 still holds.
- Budget data updates up to three times a day, so the alarm is slow by design. Credits can lag too, so the final check waits at least 24 hours after the last write.
- Local state means losing the file loses track of resources, not the resources themselves. The runbook covers recovery with `tofu import`.
- A second table is impossible inside the allowance, because 25/25 is fully used. Live tests share `verity-graph` under their own tenant.
