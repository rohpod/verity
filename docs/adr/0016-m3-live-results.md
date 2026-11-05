# 0016 — M3 live results
- **Status:** Accepted (2026-11-05). Refines [0014](0014-m2-measurements-and-evidence-cap.md) and [0015](0015-account-baseline.md); both stay in force.

## Context
M2 ran on moto, which cannot show table class, GSI delay, transaction capacity or throttling. ADR 0014 left the throttling form open, because AWS's pages list two. ADR 0015 said no AWS page settles whether OpenTofu reads `aws login` sessions. M3 ran `tests/live/` against the real `verity-graph` table on 2026-11-05.

## Decision
- **Keep both throttling paths.** The real table reported a throttled transaction as `ProvisionedThroughputExceededException`, which boto3 retries. The repository's retry for a cancelled transaction did not run. It stays, because this is one observation of one kind of overload and AWS documents the other form too.
- **Keep the capacity estimates in `capacity.py`.** Real writes matched them.
- **Live tests are the record.** `tests/live/` stays in the repo, skipped unless `VERITY_LIVE_AWS=1`, so these results can be repeated after any rebuild.

## Alternatives
| Option | Why not chosen |
|---|---|
| Remove the repository's transaction retry | One probe does not show that AWS never cancels for capacity, and the code is small and tested |
| Write the results into ADR 0014 or 0015 | Accepted ADRs are not edited |

## Consequences
**Measured**

| Check | Result |
|---|---|
| Node write | 4 units on the table, as estimated, plus 1 on GSI1 for a new node |
| Edge write | 4 units on the table, none on GSI1 |
| Evidence write | 1 unit on the table, 1 on GSI1, for a small item |
| Scan of 2 items | 1 read unit |
| GSI delay | 1.2 s for a new node to appear in `nodes_by_type`, from one sample |
| Throttled transaction | `ProvisionedThroughputExceededException`, no cancellation reasons |
| Repository write straight after the throttle | Succeeded in 1.2 s |

**Confirmed**
- The console shows the table class as DynamoDB Standard. `DescribeTable` leaves out both `TableClassSummary` and `BillingModeSummary` on this table, so a live check cannot prove the class from that call alone.
- AWS's policy simulator denies all 16 sampled never-use actions and allows `dynamodb:PutItem`. This is a simulation, not an attempted call.
- `aws login` asks for MFA.
- OpenTofu 1.13.5 with provider 6.72 reads a `login_session` profile directly. boto3 does not, so the `credential_process` profile is still needed for the live tests.
- A budget can be created on the Free plan.

**Limits**
- The throttle came from transactions of about 4,000 write units. A slow, sustained overload could behave differently.
- The first seed adds 1 GSI unit per node, about 300 units at the design target, against 10 per second on the index. That is about 30 s spread across a 6 minute seed, so the table stays the limit.
