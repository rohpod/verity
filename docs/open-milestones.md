# Milestone status: M3, M8, M9 and M10

_2026-11-06, after PR 61 merged. A milestone is ✅ only when every validation criterion in [Stage 4](stage-4-milestones.md) has passed. This page is a status record: when a milestone closes, update its row in Stage 4 and its section here._

**Update, 2026-11-07.** L15 is done: the schedule is `ENABLED`, and a real scheduled run finished at 07:30 UTC with 3 ChangeEvents ([ADR 0032](adr/0032-m8-scheduled-run.md)). The cron was a one-off `cron(30 7 * * ? *)` for that run and has been put back to `cron(0 3 * * ? *)`, which has not run yet. **M3 and M8 are closed (✅)** on the owner's report that credits were unchanged, taken before the 24-hour mark and accepted as an exception ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 5). They reopen if a later read shows less than $120. M9 stays 🔄 until the owner merges its PR, and M10 stays 🔄.

**Update, 2026-11-07, later.** The first live snapshot passed its scan and the Opus review ([ADR 0033](adr/0033-m9-live-snapshot.md)). It was built without checking a run on the 03:00 UTC cron and without a credit read after the 24-hour mark, by the owner's decision. **M9 is ✅** (PR 72 merged).

**Update, 2026-11-07, Pages.** The Pages deploy ran, and the live site was checked at desktop and phone width. The first check found the Graph page 399 px wide at 390 px, which PR 73 fixed. The re-check passed, so **M10 is ✅** ([ADR 0034](adr/0034-m11-close-decisions.md)). M11's decisions are recorded in ADR 0034, and Opus does the final review before M11 is marked done.

M3, M8, M9 and M10 are closed. Nothing on this page is waiting on a deploy or an export. What is left is the optional credit read, and M11's final review.

| Milestone | What is left | Waiting on | Earliest close |
|---|---|---|---|
| M3 | ✅ on 2026-11-07 by the owner's exception. A full L17 read has not been taken | A read at or after 10:12 UTC on 2026-11-08 ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 5) | Closed. Reopens if credits are below $120 |
| M8 | ✅ on 2026-11-07 by the same exception. L15 passed. No run on the 03:00 UTC cron has been checked | The same read | Closed. Reopens if credits are below $120 |
| M9 | ✅ on 2026-11-07: the live export, the scan and the Opus review passed, and PR 72 merged ([ADR 0033](adr/0033-m9-live-snapshot.md)) | Nothing | Closed |
| M10 | ✅ on 2026-11-07: the Pages deploy ran and the live site passed at 1280 px and 390 px, after the PR 73 fix ([ADR 0034](adr/0034-m11-close-decisions.md)) | Nothing | Closed |

The order is fixed: **L15 → first scheduled run → credit read (closes M3 and M8) → live snapshot (closes M9)**. M10's Pages URL then needs that snapshot. All of these are done.

## M3: account baseline (✅)

**Closed 2026-11-07.** The last criterion, "credits unchanged", rests on the owner's report that no credit changed and nothing was deducted, against $120. It was given before the 24-hour mark, so it is an exception ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 5), and M3 reopens if a later read shows less. Everything else passed on 2026-11-05 ([ADR 0016](adr/0016-m3-live-results.md)).

**Why it was open.** Credits can lag, so the check waits at least 24 hours after the last write ([ADR 0015](adr/0015-account-baseline.md)). M8 kept writing to the account before that read was taken, so the read moved. [ADR 0028](adr/0028-m8-review.md) decision 4 lets M8's credit read close M3 as well. With a daily schedule there is always a recent write, so the rule is now 24 hours after the latest one-off change: the 07:30 UTC run, the cron revert and the B4 invokes. That is 10:12 UTC on 2026-11-08 ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 3).

**Which baseline to use.** The records hold two numbers: $100 in the 2026-11-05 findings and $120 before M8 ([ADR 0027](adr/0027-m8-live-results.md)). Nothing records why they differ. A rise is not a charge, and onboarding activities can add credits, but that cause is **unconfirmed**. On 2026-11-07 the owner reported $0 spent and that the $100 figure may have been stated by mistake. That is the owner's report and is **not confirmed from Billing records**. Keep **$120** as the baseline, and compare the read with it.

**Closed by:** the owner's report, as above. A read at or after 10:12 UTC on 2026-11-08 would make it a full check and is recommended.

## M8: deploy and first live crawl (✅)

Closed on 2026-11-07. L15 passed, and the credit criterion rests on the owner's early report ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 5).

| Criterion | State | Source |
|---|---|---|
| Function URL pricing confirmed | Passed | [ADR 0025](adr/0025-m8-deploy-and-crawl.md) |
| All 5 functions classify as expected | Passed | ADR 0027, L11 |
| An unsigned call to mock-openai is refused | Passed | ADR 0027, L7 |
| Unused `bedrock:InvokeModel` finding, and no Bedrock use in CloudTrail | Passed | ADR 0027, L12 and L14; ADR 0028 |
| Second crawl is idempotent | Passed | ADR 0027, L13 |
| Destroying the estate then applying rebuilds it cleanly | Passed | ADR 0027, L16; ADR 0028 |
| A scheduled run (L15) | **Passed** on 2026-11-07 | A real cron run at 07:30 UTC, `finished_at` set, 3 ChangeEvents ([ADR 0032](adr/0032-m8-scheduled-run.md)) |
| Credits unchanged (L17) | **Passed on the owner's early report** | Reported unchanged on 7 Nov, before the 24-hour mark ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 5). Reopen if a later read shows less |

**Why L15 was open, and how it closed.** L15 was enabled once, and then the L16 rebuild reset the schedule to `DISABLED`. It was applied again at 07:08:38 UTC on 2026-11-07 with a one-off `cron(30 7 * * ? *)`, a local edit that was never committed. The 07:30 UTC run was a real scheduled run: CloudTrail shows the Scheduler service assuming `verity-crawl-scheduler-role`. The cron was reverted at 10:10:40 UTC. The schedule is configured for 03:00 UTC, and that cron has not run yet ([ADR 0032](adr/0032-m8-scheduled-run.md)).

**How L17 closed.** The full read would be at least 24 hours after the latest of the 07:30 UTC run, the cron revert and the B4 invokes, so at or after 10:12 UTC on 2026-11-08 ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 3). The owner chose to close on an earlier report of no change, and decision 5 records that.

**To close:**
1. **Done 2026-11-07.** L15 was applied with `-var schedule_state=ENABLED`. Plain `tofu apply` sets the schedule back to `DISABLED`, so always pass the variable.
2. **Done.** The plan was 0 add, 4 change, 0 destroy, as expected: the schedule changed and the code of **three** functions was updated, and nothing else:
   - `verity-crawler`, because the `trail_shows_ai` fix (`discovery/pipeline.py`, `discovery/usage.py`) and `graph/traversals.py` changed after L16, and PR 65 added `AWS_ERRORS` to `graph/dynamodb/client.py`.
   - `support-assistant` and `contract-insights`, only because of that PR 65 change: both zips bundle `graph/dynamodb/client.py` (`APP_CORE` in `scripts/build_lambdas.py`), and nothing else in them changed.

   Anything beyond that would have been a stop. In particular `talent-screening`, `shadow-summariser`, `invoice-renderer`, `mock-bedrock` and `mock-openai` bundle none of the changed files, so their code hashes must not move. `verity-probe`'s zip also bundles `client.py`, but the probe is destroyed (`enable_probe = false`), so it is not in the plan and the crawler never sees it. This list comes from reading `build_lambdas.py` and git history, not from a plan or a live table: the `tofu plan` output decides.
3. **Done.** Exactly one new run, `run:20261107T073045.159088Z`, with `finished_at` set.
4. **Done, early.** The owner reported credits unchanged on 2026-11-07, recorded in [ADR 0032](adr/0032-m8-scheduled-run.md) decision 5. M8 is ✅.

**The new code changed the data.** The first scheduled run recorded **three** ChangeEvents, with AFFECTS edges to `verity-crawler`, `support-assistant` and `contract-insights`, and `resources_changed` was 3. The old and new snapshots differ only in `code_sha256` and `config_hash`. That is why [ADR 0029](adr/0029-m9-snapshot-export.md) decision 13 holds the snapshot until M8 closes. `verity assess --target dynamodb` is still needed before the export.

**This had a deadline.** Crawler evidence lasts 30 days, and only a crawl renews it. With the schedule off, the evidence from 2026-11-06 would have started expiring around 29 Nov. The schedule is now on, so crawls renew it. A later export still needs a fresh `verity assess --target dynamodb` (see the plan in [ADR 0032](adr/0032-m8-scheduled-run.md)), and the schedule must still be `ENABLED` when it is made.

**Known limits that do not block closing:**
- Nobody has shown that the boundary stops a real Bedrock call. The IAM simulator is the accepted evidence, because a live call is forbidden (ADR 0028, decision 5).
- CloudTrail event history cannot show SageMaker's invoke calls, so L14 says nothing about SageMaker either way.
- The apps, the simulator and the probe were not run again after L16. They run from identical code.

## M9: snapshot export (✅)

PRs 59 to 61 built the export and passed its redaction review. The first live export ran on 2026-11-07 ([ADR 0033](adr/0033-m9-live-snapshot.md)).

| Criterion | State |
|---|---|
| Scans of a snapshot from live data find no account ID, Function URL host, env value or email | **Passed:** 0 scan hits, and the Opus review compared the file with the real values |
| Schema validates | Passed on live data |
| Every record has provenance, and the file has its `as_of` | Passed on live data: `as_of` 2026-11-07T12:20:39.767Z |

**Code for PR C, proved on the real table on 2026-11-07:**
1. **The live export path.** Read through `GraphRepository.load_graph()`, write `data_source: live`, and use now as `as_of`, not the start of the day, or the stale check refuses a good graph ([ADR 0030](adr/0030-m9-redaction-review.md)).
2. **The decision commit SHA lookup** (ADR 0029, decision 9). The snapshot gains `decision_commits` (`commit_sha` is null in a fixture export), a live export refuses if a decision has no commit, and the scanner exempts only a 40-hex value under the key `commit_sha`.

**Steps, all done except the merge:**
3. With approval, run `verity assess --target dynamodb`, because export refuses a stale graph. It took 29 minutes for 4 records (ADR 0033).
4. Export, and scan the first live file before doing anything else with it.
5. Opus reviews the redaction, because a commit to a public repository cannot be taken back.
6. The owner confirms and merges a PR that adds `web/public/data/snapshot.json`. Mark M9 ✅.

**Known limit that does not block closing:** the listed fields and scan rules cannot prove that nothing sensitive exists beyond them. Free text from reviewed YAML is only scanned. That is why the Opus review is the last check (ADR 0030).

## M10: dashboard (✅)

Built in one PR ([ADR 0031](adr/0031-m10-dashboard.md)): the six screens, the System profile, the audit trail and `stale_by_change` in TypeScript with parity tests, the development-only fixture flow, Playwright at 390 px, CI for `web/`, and `.github/workflows/pages.yml`. Everything so far runs against the recorded fixture and a generated mini snapshot.

| Criterion | State |
|---|---|
| Typecheck and build pass | Passed. **Gap found in review:** `vite build` copied `web/public/` into `dist/`, so `check:dist` would have failed in CI and in the Pages workflow once a snapshot was committed. Fixed with `build.copyPublicDir: false`, and a test that builds with a sample file in `web/public/data/` and fails without the fix |
| `snapshot.json` is the only data source | Passed: a test fails on any other `fetch` or snapshot import, and the page's Content-Security-Policy allows only its own origin. A Playwright run against the production build under `/verity/` fails on any console error, CSP violation or off-origin request |
| Every view shows provenance and the timestamp | **Gap found in review, now fixed:** the timestamp was on every route, but the Graph explorer's lists (neighbourhood, Impact, Stale) showed no provenance badge, so synthetic records there were unlabelled, and `routes.test.tsx` exempted `/graph` from the badge check. They now show a badge for each record, at phone width too, and only `/about` (which shows no records) is exempt. The boundary note for VC-060 on `support-assistant` was also missing from the Controls detail and is now shown there. Checked on the fixture and the mini snapshot only |
| Works at phone width | Passed: Playwright at 390 px and at desktop width, on the dev server and on the production build |
| Pages URL works | **Passed** on 2026-11-07, after one fix. The first check at 390 px found the Graph page 399 px wide, because the live snapshot has long node ids (PR 73). The re-check passed: every route at 1280 px and 390 px has 0 overflow, shows `data source: live` with `Snapshot as of 2026-11-07 12:20:39 UTC`, no fixture banner, and no console or off-origin errors. Details in [ADR 0034](adr/0034-m11-close-decisions.md) |

**Closed 2026-11-07.** The deploy job ran and passed for PR 72 and for the fix in PR 73, and the live site was checked as above.
