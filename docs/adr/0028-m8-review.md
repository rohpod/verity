# 0028 — M8 review: why the seed and assess were slow, and what is still open
- **Status:** Accepted (2026-11-06). Refines [0027](0027-m8-live-results.md), and replaces its stated cause in decision 3 and the wording of its decision 4. 0025, 0026 and the rest of 0027 stay in force. M8 is not closed: the scheduled run (L15) and the credit read (L17) are still to come.

## Context
The end-of-milestone review read ADRs 0025 to 0027 against the code and the account. It was read-only on AWS: nothing was created, changed or invoked, and no Bedrock or SageMaker call was made. CloudWatch metrics were not read. Every value below was measured on 2026-11-06.

## What the review measured
**The seed and the assess were slow because of the operator's credentials, not throttling.**
- The `verity` profile uses `credential_process`, which runs `aws configure export-credentials`. `aws login` credentials had 787 s left when read, inside botocore's 900 s refresh window.
- A client in that window refreshes on each call. 20 reads ran the process 40 times and took 595 ms each. With the same credentials held as static values, a read took 164 ms.
- Run under moto, the seed makes 986 API calls and the assess 4,056. The live runs took 649 s and 2,469 s, which is 0.66 s and 0.61 s a call.
- The estate's writes averaged under 3 units a second, against 15 provisioned. Throttling is not needed to explain the time, and the backoff path was probably not exercised. No throttle count was read, so that is an inference.

**The events in L14 are not model use.** All 7 Bedrock events and all 39 SageMaker events are `List*` calls by `AWSServiceRoleForResourceExplorer`, dated 2026-11-05, the day before any M8 resource existed. Event history cannot show SageMaker's invoke calls (`ai_signals.yaml` lists no events for them), so L14 is no evidence about SageMaker either way.

**The findings hold after the rebuild.** Assessing a copy of the live table in memory gives 29 high and nothing to write. VC-060 evidence still fails on `support-assistant`, and `shadow-summariser` is still a high Candidate. L16's "high findings hold" was left out of 0027's table, and this closes it.

**The rest of the state matches.**
| Check | Result |
|---|---|
| Deployed code | All 8 hashes equal a fresh build of `main` |
| Boundary | On all 9 roles. Its policy holds the three deny patterns |
| Function URL | `AWS_IAM`, no resource policy |
| Schedule | `DISABLED`, `cron(0 3 * * ? *)` UTC, no Scheduler or async retries |
| Log groups | All 8 at 3-day retention |
| Tags | `shadow-summariser`, `talent-screening` and `invoice-renderer` have none |
| Account | No trails, no auto-scaling. Only approved resource types in the state |
| Full scan | 3,921 items, 664 nodes, 1,307 edges: 7.4 s with static credentials |
| Last write | 14:18:02 UTC, the L16 crawl |

## Decision
1. **The cause in 0027's decision 3 is replaced.** The times stay as measured, but they describe `credential_process` with `aws login`. They are not what the table can do. About 2.7 and 11 minutes is the estimate with static credentials, from the call counts. Neither has been measured.
2. **The scheduled crawl is not affected.** It runs on the function's role, with no `credential_process`. Live crawls took 17 to 22 s against the 120 s limit, though the time will grow with the table ([0014](0014-m2-measurements-and-evidence-cap.md)).
3. **0027's decision 4 is reworded.** As written, the schedule could never be checked. The schedule is enabled for L15 and left `ENABLED` once one run is checked. A plain `tofu apply` resets it to `DISABLED`, which is how L16 undid L15.
4. **L17 comes after the first scheduled run.** That run is a write, so the credit read must be at least 24 hours after it, not after L16. The same read can close M3's last criterion.
5. **The simulator's evidence is enough for M8, and the claim must match it.** Deny in a boundary is a fixed part of IAM's evaluation, the control shows the deny comes from the boundary, and a live call is forbidden. The roles and the boundary were recreated in L16 from the same code, and L9 ran before that. The UI must say that IAM's simulator shows the boundary denies the call, and that no live call was tried. It must not say the grant "is ineffective" as a fact.
6. **The classifier gap is recorded, not fixed here.** 0027's decision 2 is true of VC-060, because `_proves` checks the event's name. `trail_shows_ai` does not: any successful call from a function's own role to a listed source counts, so `ListFoundationModels` would score `confirmed_usage`. The L14 events are excluded only because their role is not a function's role. The live results are unaffected.

## Alternatives
| Option | Why not chosen |
|---|---|
| Edit 0027 | Accepted ADRs are not edited |
| Re-run the assess to prove the findings | About 41 minutes, and the in-memory copy answers the same question with no writes |
| Read CloudWatch for a throttle count | The call counts explain the time. `GetMetricStatistics` is not named on the pricing page, so its price is only inferred |
| Mark M8 done now | L15 and L17 are criteria, and neither has happened |

## Consequences
- **Not proved:** a scheduled run, unchanged credits, and that the boundary blocks a real call.
- **Not re-run since L16:** the apps, including SigV4 against the recreated Function URL, the simulator and the probe. They run from identical code.
- **Static credentials last about 15 minutes,** so that shortcut needs care with a long assess.
- **The CLI's "expect pauses while it throttles" message** is misleading, and needs changing with the credential fix.
