# 0032 — M8 scheduled run: L15 passed on a one-off cron, and the credit read waits for 10:12 UTC on 8 Nov
- **Status:** Accepted (2026-11-07), with the credit read recorded as an early, owner-accepted exception (decision 5). Refines [0015](0015-account-baseline.md), [0027](0027-m8-live-results.md) and [0028](0028-m8-review.md). [0025](0025-m8-deploy-and-crawl.md) decision 8 stays in force: the cron was put back to `cron(0 3 * * ? *)`. M3 and M8 are closed on the owner's report, not on a read that meets decision 3.

## Context
[0028](0028-m8-review.md) left two things open for M8: a scheduled run (L15) and the owner's credit read (L17). The schedule had been `DISABLED` since the L16 rebuild, so nothing moved until it was applied. Every value below was read on 2026-11-07 in eu-north-1, with read-only calls, except where it says the owner reported it. Bedrock and OpenAI were not invoked. Only the mocks ran.

## Results
| # | Step | Measured | Expected | Held? |
|---|---|---|---|---|
| L15 | `tofu apply -var schedule_state=ENABLED` at 07:08:38 UTC, from `main` at `756cc60` | Plan 0 add, 4 change, 0 destroy: `verity-crawl-daily`, `verity-crawler`, `support-assistant`, `contract-insights`. The schedule moved from `DISABLED` to `ENABLED`. All 8 deployed code hashes equal the local `.build` zips | The same four changes | Yes |
| L15 | The run at 07:30 UTC | CloudTrail shows `scheduler.amazonaws.com` assuming `verity-crawl-scheduler-role` at 07:30:43 UTC. REPORT: Duration 13,964.91 ms, Billed 14,584 ms, 256 MB, Max Memory 146 MB, Init 618.58 ms. Log line: `crawl finished: 8 functions, 30 written` | One scheduled run | Yes |
| L15 | The run's record | `run:20261107T073045.159088Z`, the only run that day. `finished_at` 2026-11-07T07:30:57.825961Z. Summary: functions 8, roles 9, tables 1, resources_new 0, resources_changed **3**, resources_ended 0, candidates 1, evidence_written 5, manifests_invalid 0, manifest_functions_missing 0, trail_events 11, largest_evidence_bytes 1,359 | `finished_at` set | Yes |
| L15 | What it wrote | Exactly 3 ChangeEvents, with AFFECTS edges to `verity-crawler`, `support-assistant` and `contract-insights`. Old and new config snapshots differ only in `code_sha256` and `config_hash`. 5 Evidence items: 3 config snapshots, plus VC-060 for `sys:support-assistant` (fail, `bedrock:InvokeModel` unused) and `sys:contract-insights` (pass) | Three ChangeEvents | Yes |
| L15 | Classification | `declared` 3, `none` 4, `probable` 1, as in L11. The other 5 functions were not modified on 2026-11-07 | As L11 | Yes |
| L15 | Trail events | 7 became 11, through 4 Bedrock `List*` events by Resource Explorer on 2026-11-07. No `Invoke*` or `Converse*` events | No invocation | Yes |
| Revert | Cron put back at 10:10:40 UTC | Plan 0 add, 1 change, 0 destroy, changing only `schedule_expression`. AWS then showed `ENABLED`, `cron(0 3 * * ? *)`, UTC | One change | Yes |
| B4 | One invoke each at 10:11 UTC | `support-assistant` 200 in 2,349.52 ms, `contract-insights` 200 in 2,381.21 ms, both 512 MB and under [0025](0025-m8-deploy-and-crawl.md)'s 3-second limit. One new usage item each (1 to 2). `mock-bedrock` and `mock-openai` each ran once with no errors logged. Mock only. `mock-openai` running re-tests the signed Function URL call after L16 | Both return | Yes |
| A3 | Baseline | The owner reports $0 spent, and that the $100 in the 2026-11-05 findings may have been stated by mistake. **This is the owner's report, not confirmed from Billing records.** The baseline stays **$120** | A cause | **Not confirmed** |
| L17 | Owner's reports on 2026-11-07, at about 10:20 UTC and again at about 11:05 UTC | The owner reports that no credit changed and no money was deducted. The time of the Billing read was not given. Both are under 24 hours after the cron revert and B4, so **neither meets decision 3** | Unchanged | **Owner-accepted, early (decision 5)** |

## Decision
1. **L15 passed on the 07:30 UTC run.** Its criterion is one scheduled run with `finished_at` set, and [0028](0028-m8-review.md) decision 3 asks for one run to be checked. No run at 03:00 UTC is needed as evidence.
2. **This was an owner-accepted exception.** [0027](0027-m8-live-results.md) listed "Change the cron to test the schedule sooner" as a rejected alternative, because the tested config would differ from the shipped one. The cron was changed anyway, to `cron(30 7 * * ? *)`, so that the first run and the credit read came a day sooner. The edit was local and never committed, so the tree was not clean as the runbook's build step requires. It touches no file in a zip: all 8 deployed code hashes equal the local zips. The cron was reverted, and [0025](0025-m8-deploy-and-crawl.md) decision 8 is not superseded.
3. **The L17 read comes at least 24 hours after the latest of the 07:30 UTC run, the cron revert and B4.** That is 10:12 UTC on 2026-11-08 or later. Recurring daily crawls do not restart the wait: each crawl writes a run, so [0015](0015-account-baseline.md)'s "24 hours after the last write" cannot hold with a daily schedule. This refines [0015](0015-account-baseline.md) and [0028](0028-m8-review.md) decision 4. A read taken sooner is not the L17 read.
4. **Wording.** The schedule is configured for 03:00 UTC. Nothing here shows that it has run at 03:00 UTC or that it runs daily.
5. **M3 and M8 are closed on an early report, by the owner's decision.** On 2026-11-07, about 11:05 UTC, the owner said no credit had changed and chose to close both milestones without waiting for 10:12 UTC on 2026-11-08. That is an exception to decision 3, and it is recorded as one: the 24-hour rule was not met, and credits can lag. The baseline is still **$120**. The owner expects no change, and will reopen M3 and M8 if a later read shows credits below $120. A read at or after 10:12 UTC on 2026-11-08 would turn this into a full L17 and is recommended, but nothing waits on it.

## Alternatives
| Option | Why not chosen |
|---|---|
| Leave the cron at 03:00 UTC and wait for 8 Nov | Costs a day. The owner accepted the exception instead, with the exception recorded here |
| Invoke the crawler by hand and call it L15 | Skips the scheduler, which is what L15 tests |
| Keep `cron(30 7 * * ? *)` | It differs from [0025](0025-m8-deploy-and-crawl.md) decision 8 and from the shipped config |
| Count the early report as a full L17 | It is under 24 hours after the cron revert and B4. It is recorded as an exception instead (decision 5) |
| Wait for 10:12 UTC on 8 Nov before closing | The owner chose not to wait. The cost is that the closing read is early |

## Consequences
- **Not proved:** a credit read taken 24 hours after the latest one-off change (see decision 5), and that the schedule fires on `cron(0 3 * * ? *)`. The 03:00 UTC cron has not run yet.
- **Reopening:** if credits fall below $120 later, M3 and M8 are reopened. Charges can lag, and a daily crawl is a write that the 24-hour rule cannot wait out.
- **A3 stays unconfirmed.** The cause of the $100 and $120 figures is the owner's report only. $120 is the baseline.
- **Evidence is renewed from now on.** The schedule is on, so crawls renew crawler evidence, which would have started expiring around 29 Nov. A later export still needs a fresh `verity assess --target dynamodb`.
- **The deployed crawler now carries the `trail_shows_ai` fix** ([0028](0028-m8-review.md) decision 6).
- **The apps, the simulator and the probe** were not run again beyond B4. The probe is destroyed.
- **Still not proved:** that the boundary stops a real Bedrock call ([0028](0028-m8-review.md) decision 5). The simulator's answer is the accepted evidence.
