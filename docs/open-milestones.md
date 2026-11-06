# Why M3, M8 and M9 are not complete

_2026-11-06, after PR 61 merged. A milestone is ✅ only when every validation criterion in [Stage 4](stage-4-milestones.md) has passed. This page is a status record: when a milestone closes, update its row in Stage 4 and its section here._

The work is mostly done, and nothing here is a known failure. Each milestone is waiting on something that has not happened yet: 24 hours passing, a scheduled run, or a live export.

| Milestone | What is left | Waiting on | Earliest close |
|---|---|---|---|
| M3 | One credit read | M8's first scheduled run, then 24 hours | 8 Nov 2026, if L15 is applied before 03:00 UTC on 7 Nov |
| M8 | A scheduled run (L15), then a credit read (L17) | The owner's approval of L15 | The same credit read |
| M9 | Two pieces of code, then a live export, Opus review and a merged snapshot | The code can start now. The live run waits for M8 | After M8 closes |

The order is fixed: **L15 → first scheduled run → credit read (closes M3 and M8) → live snapshot (closes M9)**. M10's Pages URL then needs that snapshot. Nothing moves until L15 is approved.

## M3: account baseline (🔄)

**Criterion still open:** "credits unchanged". Everything else passed on 2026-11-05 ([ADR 0016](adr/0016-m3-live-results.md)).

**Why it is still open.** Credits can lag, so the check waits at least 24 hours after the last write ([ADR 0015](adr/0015-account-baseline.md)). M8 kept writing to the account before that read was taken, so the read moved. [ADR 0028](adr/0028-m8-review.md) decision 4 lets M8's credit read close M3 as well.

**Which baseline to use.** The records hold two numbers: $100 in the 2026-11-05 findings and $120 before M8 ([ADR 0027](adr/0027-m8-live-results.md)). Nothing records why they differ. A rise is not a charge, and onboarding activities can add credits, but that cause is **unconfirmed**. The owner should check the credit history in the Billing console, record the cause and compare the read with **$120**.

**To close:** the owner's credit read matches the baseline. Mark M3 ✅.

## M8: deploy and first live crawl (🔄)

Stage 4 showed ⬜ until this page was added, which understated it: everything except two criteria passed on 2026-11-06, and it is now 🔄.

| Criterion | State | Source |
|---|---|---|
| Function URL pricing confirmed | Passed | [ADR 0025](adr/0025-m8-deploy-and-crawl.md) |
| All 5 functions classify as expected | Passed | ADR 0027, L11 |
| An unsigned call to mock-openai is refused | Passed | ADR 0027, L7 |
| Unused `bedrock:InvokeModel` finding, and no Bedrock use in CloudTrail | Passed | ADR 0027, L12 and L14; ADR 0028 |
| Second crawl is idempotent | Passed | ADR 0027, L13 |
| Destroying the estate then applying rebuilds it cleanly | Passed | ADR 0027, L16; ADR 0028 |
| A scheduled run (L15) | **Open** | Read on 2026-11-06: `verity-crawl-daily` is `DISABLED` |
| Credits unchanged (L17) | **Open** | Not yet read |

**Why L15 is open.** L15 was enabled once, and then the L16 rebuild reset the schedule to `DISABLED`. A read at about 17:25 UTC on 2026-11-06 showed it `DISABLED`, last changed at 14:16:49 UTC, which is the rebuild. No scheduled run has happened.

**Why L17 is open.** The first scheduled run is a write, so the read must come at least 24 hours after it.

**To close:**
1. Approve L15, then run it from a clean, current `main`: rebuild the zips, then `tofu plan` and `tofu apply` with `-var schedule_state=ENABLED`. Plain `tofu apply` sets the schedule back to `DISABLED`, so always pass the variable.
2. Check the plan. It should change the schedule and also update the crawler, because the `trail_shows_ai` fix merged after L16. Anything beyond that is a stop.
3. The next day, confirm exactly one new run with `finished_at` set.
4. At least 24 hours after that run, the owner reads the credits. Record the results in a new ADR and mark M8 ✅.

**The new crawler changes the data.** Its code hash differs, so the first scheduled run is expected to record a ChangeEvent and new evidence for it. That is why [ADR 0029](adr/0029-m9-snapshot-export.md) decision 13 holds the snapshot until M8 closes. It also means `verity assess --target dynamodb` must run before the export.

**This has a deadline.** Crawler evidence lasts 30 days, and only a crawl renews it. With the schedule off, the evidence from 2026-11-06 starts expiring around 29 Nov and goes stale around 6 Dec.

**Known limits that do not block closing:**
- Nobody has shown that the boundary stops a real Bedrock call. The IAM simulator is the accepted evidence, because a live call is forbidden (ADR 0028, decision 5).
- CloudTrail event history cannot show SageMaker's invoke calls, so L14 says nothing about SageMaker either way.
- The apps, the simulator and the probe were not run again after L16. They run from identical code.

## M9: snapshot export (🔄)

Stage 4 also showed ⬜ here. PRs 59 to 61 built the export and passed its redaction review, so it is now 🔄. Every result so far comes from the recorded fixture and hand-built graphs. The criterion is about **live data**, and no live snapshot exists.

| Criterion | State |
|---|---|
| Scans of a snapshot from live data find no account ID, Function URL host, env value or email | **Open:** a live export is not built, and `verity export` without `--local` is refused |
| Schema validates | Passed on the fixture, not yet on live data |
| Every record has provenance, and the file has its `as_of` | Passed on the fixture, not yet on live data |

**Code still to write (PR C), which can start now:**
1. **The live export path.** Read through `GraphRepository.load_graph()`, write `data_source: live`, and use now as `as_of`, not the start of the day, or the stale check refuses a good graph ([ADR 0030](adr/0030-m9-redaction-review.md)).
2. **The decision commit SHA lookup** (ADR 0029, decision 9). It is **not built**, and the snapshot schema has no field for it. It needs the field, the lookup, a refusal when a live export cannot find a SHA, and an exact-shape exemption from the digit rule, because a SHA is 40 hex digits.

**Steps that wait for M8 to close:**
3. With approval, run `verity assess --target dynamodb`, because export refuses a stale graph. It took 41 minutes last time, slowed by credential refreshes (ADR 0028).
4. Export, and scan the first live file before doing anything else with it.
5. Opus reviews the redaction, because a commit to a public repository cannot be taken back.
6. The owner confirms and merges a PR that adds `web/public/data/snapshot.json`. Mark M9 ✅.

**Known limit that does not block closing:** the listed fields and scan rules cannot prove that nothing sensitive exists beyond them. Free text from reviewed YAML is only scanned. That is why the Opus review is the last check (ADR 0030).
