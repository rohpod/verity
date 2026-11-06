# 0027 — M8 live results: what ran on AWS, what it measured and what is still open
- **Status:** Accepted (2026-11-06). Refines [0025](0025-m8-deploy-and-crawl.md) and [0026](0026-m8-cold-start.md); both stay in force. M8 is not closed: an end-of-milestone review by Opus, a scheduled run and the owner's credit check are still to come.

## Context
M8 was the first milestone since M3 to change the account. PR A built the crawler, the probe and their zips, PR B wrote the estate as OpenTofu, and PR C ran it, one approved step at a time ([runbook](../runbooks/m8-deploy.md)). Nothing was run against Bedrock or SageMaker. Every value below was measured on 2026-11-06 in eu-north-1. The owner read the credits before (**$120**) and still has to read them 24 hours after the last write.

## Results
| # | Step | Measured | Expected | Held? |
|---|---|---|---|---|
| L1 | Zip build from a clean tree | 9 zips, deterministic. Final sizes in KB: crawler 7295, probe 3432, support-assistant 3493, contract-insights 3491, shadow-summariser 6, talent-screening 2, mock-openai 1, invoice-renderer and mock-bedrock under 1. Deployed hashes equal a fresh build | Under 8 MB | Yes |
| L2 | `verity seed --target dynamodb` | 188 nodes, 288 edges, **649 s** | About 2.1 min | **No, 5 times slower** |
| L3 | `tofu plan` | 46 to add, 0 to change, 0 to destroy. Nothing in `module.table` or `module.guardrails` | Approved types only | Yes |
| L4 | `tofu apply` | 46 added in 85 s. The Free plan accepted IAM, Scheduler and SSM | All created | Yes |
| L5 | First run of the 5 apps, 128 MB | `support-assistant` and `contract-insights` **timed out at 10 s**. `shadow-summariser` 4,662 ms, `talent-screening` 15.8 ms, `invoice-renderer` 2.5 ms. 0 usage items | All return, 2 usage items | **No** |
| L5 | After ADR 0026 (bytecode, 512 MB for the two pydantic apps) | `support-assistant` 2,210 ms, `contract-insights` 2,265 ms, `shadow-summariser` 4,448 ms, `talent-screening` 17.5 ms, `invoice-renderer` 7.2 ms. 2 usage items | All return, 2 usage items | Yes |
| L6 | Init Duration, all runs | 54 to 88 ms | Recorded | Yes |
| L7 | Unsigned POST to the Function URL | **403 `Forbidden`**. `mock-openai` logged no run (3 report lines before and after, which can lag) | 403, function did not run | Yes |
| L8 | `verity-probe`, 512 MB | `AccessDeniedException` twice, 2.48 s from the caller. The table held 949 items before and after | Two `AccessDeniedException` | Yes |
| L9 | IAM simulator, `bedrock:InvokeModel` on `support-assistant-role` | `explicitDeny` from `verity-function-boundary`, then `allowed` with an allow-all boundary | Deny, then allow | Yes |
| L10 | Remove the probe | 0 to add, 0 to change, 1 to destroy | Probe gone before the crawl | Yes |
| L11 | First `verity crawl` | **18 s.** 8 functions. `declared=3`, `none=4`, `probable=1`, 1 Candidate. 21 Evidence items, 45 evidence edges, 18 resources, 0 invalid manifests. `largest_evidence_bytes` **1,359**, 7 trail events | The classification table | Yes |
| L12 | `verity assess --target dynamodb` | **2,469 s (41 min).** 29 high. Wrote 65 `applies_to`, 873 assessment edges, 433 assessments. VC-060 fails on `support-assistant` and `shadow-summariser` is a high Candidate | 29 high, about 6.6 min | **Findings held, time did not (6 times)** |
| L13 | Second crawl | **17 s.** Wrote only `1 runs`. `evidence_written=0`, `resources_new=0` | Writes only the run | Yes |
| L14 | CloudTrail, `bedrock.amazonaws.com` | **7 events**, all `List*` by the `resource-explorer-2` service. No `Invoke*` or `Converse*` | None | **Differs in count, not in meaning** |
| L15 | Schedule `ENABLED` | Applied at 14:05 UTC, 1 change, cron `0 3 * * ? *`, no retries | Next day: one run, `finished_at` set | **Not yet checked** |
| L16 | `tofu destroy -target=module.estate`, then `tofu apply`, then a crawl | 45 destroyed in 18 s, 45 added in 73 s. Table (3,918 items) and budget untouched. The functions' hashes are identical. The crawl took 22 s and wrote only `1 runs` | Table and budget untouched, same hashes | Yes |
| L17 | Credits 24 hours after the last write | **Not yet read** | Unchanged | **Open (owner)** |

The first L5 run and its fix are recorded in [0026](0026-m8-cold-start.md). L6 measured `support-assistant` at 2.2 s after the fix, under the 3-second limit.

## Decision
1. **The 16 KB evidence cap stays.** The largest evidence item was 1,359 bytes, less than a tenth of it. This closes the note from [0021](0021-m6-discovery.md).
2. **The Bedrock-source events do not count as use, and VC-060 needs no change.** Resource Explorer lists Bedrock objects itself. They carry no `Invoke*` or `Converse*` name, so no AI action in `ai_signals.yaml` matches them. The runbook's "none" is read as "no model invocation".
3. **The time estimates in the runbook are replaced by the measured ones.** A first seed takes about 11 minutes and a first full assess about 41 minutes. The CLI's estimates and the milestone notes were low by 5 to 6 times. They assume the provisioned rate, and the cause of the gap is not confirmed: the likely one is that the client backs off when the table throttles.
4. **The schedule stays `DISABLED` until the first scheduled run is checked.** The rebuild in L16 brought it back to the default. It is enabled with `-var schedule_state=ENABLED`.

## Alternatives
| Option | Why not chosen |
|---|---|
| Raise the evidence cap | The largest item is under a tenth of it |
| Filter the Resource Explorer events out of the crawler | It would hide that a service lists Bedrock objects, and the VC-060 matching already ignores them |
| Re-assess after L16 | Takes 41 minutes and was not in the approved list. The crawl wrote no new evidence, so no change is expected |
| Change the cron to test the schedule sooner | The tested config would differ from the shipped one |

## Consequences
- **Not proved on AWS:** a scheduled run (L15), and that the findings still hold at 29 after L16, which is expected but was not re-assessed.
- **Not proved:** that the boundary blocks a real Bedrock call. The simulator's answer is the evidence, by the owner's choice ([0025](0025-m8-deploy-and-crawl.md)). `LeadingKeys` is proved by a real refused write.
- **Cold start and Init Duration:** the first L5 result shows 128 MB was too small for the pydantic apps, fixed by [0026](0026-m8-cold-start.md). `shadow-summariser` stays slow at 4.4 s on a cold call at 128 MB, because it loads boto3 and nothing waits on it.
- **L16 deleted the log groups,** so the original REPORT lines survive only in this ADR and the PR. Three-day retention would have removed them anyway.
- **The ADR 0026 estimate** (about 2.3 s at 512 MB with bytecode) was met: 2.2 s measured.
- **Credits:** unchanged is a requirement for closing M8 and is not yet checked.
