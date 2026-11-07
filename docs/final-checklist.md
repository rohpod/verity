# Final checklist: everything still pending

_Written 2026-11-06 at about 20:00 UTC, with `main` at PR 65. Work from top to bottom and tick items as they finish. Background: [why M3, M8 and M9 are open](open-milestones.md) and the [M10 and M11 plan](m10-m11-plan.md)._

**Where things stand (2026-11-07).** M0 to M10 are ✅: M3 and M8 closed on the owner's early credit report ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 5), M9 on the live snapshot ([ADR 0033](adr/0033-m9-live-snapshot.md)), and M10 on the Pages check, after one phone-width fix ([ADR 0034](adr/0034-m11-close-decisions.md)). M11 is ⬜: its decisions are recorded in [ADR 0034](adr/0034-m11-close-decisions.md), and Opus does the final review before it is marked done. The live site is https://rohpod.github.io/verity/.

**The path:** L15 → first scheduled run → credit read (closes M3 and M8) → live snapshot (closes M9) → Pages check (closes M10) → M11.

## Dates

| When | What | If missed |
|---|---|---|
| 03:00 UTC (08:30 IST), daily | The scheduled crawl, as configured. It has not run at this time yet: the only scheduled run so far was at 07:30 UTC under a temporary cron. Never run an assess across this time | Two writers at once ([ADR 0014](adr/0014-m2-measurements-and-evidence-cap.md)): wait and repeat the assess |
| About 29 Nov 2026 | Evidence from 2026-11-06 would start expiring if the schedule were off, and goes stale around 6 Dec. The schedule is on, so crawls renew it. Confirm it is still `ENABLED` | Controls lose their fresh evidence |
| 2 Dec 2026 | `euaia-art50-2-legacy` and `euaia-art5-new` take effect, so a later snapshot can differ | Nothing breaks: review the difference |
| 15 Mar 2027 | Start a refresh, only if the owner asks for one ([ADR 0034](adr/0034-m11-close-decisions.md) decision 11) | Less buffer |
| **1 Apr 2027** | **Hard deadline** for the last live snapshot | |
| **4 May 2027** | The Free plan ends | Finish any teardown before this |

## A. Before L15

- [x] **A1. Merge Sonnet's `docs/m11-prep` PR**, once it is open and CI passes. It holds docs only. (Merged, PR 66.)
- [x] **A2. Fix `web/src/test/build.test.ts`, which blocks the snapshot PR.** It throws if `web/public/data` exists, which is where the live snapshot goes. Reproduced: with a snapshot in place, `npm test` gave 1 failed and 92 passed, while every other web check passed. Give the test a temporary `publicDir` so it never touches the repo folder. It must still fail with `copyPublicDir: true`. This changes no Lambda zip. (Done, PR 68.)
- [x] **A3. Check the credit history in Billing.** Record why credits went from $100 to $120. The cause is unconfirmed. On 2026-11-07 the owner reported $0 spent and that the $100 figure may have been stated by mistake. That is the owner's report, not confirmed from Billing records. The baseline stays $120.
- [ ] **A4. Hold code changes** in `core/`, `sdk/`, `apps/`, `mocks/`, `crawler/` and `content/rules/ai_signals.yaml` until the snapshot is published. They can change the zips and put `main` ahead of what is deployed. This includes the `credential_process` fix (M11 step 2) if it touches a file in a zip.

## B. L15: enable the schedule (AWS change, needs approval)

Run from the main checkout, because the OpenTofu state is there. Nobody else may be using that checkout.

- [x] **B1. Get a clean tree and a fresh build:**
  ```sh
  git switch main && git pull --ff-only
  git status            # must be clean
  export AWS_PROFILE=verity
  uv run python scripts/build_lambdas.py
  cd infra && tofu plan -var schedule_state=ENABLED
  ```
  Deviation: the tree was not clean on 2026-11-07. The cron in `infra/modules/estate/scheduler.tf` was a local, uncommitted edit (see ADR 0032, decision 2). It touches no zip.
- [x] **B2. Check the plan.** Expected: 0 to add, 4 to change, 0 to destroy: `verity-crawl-daily`, `verity-crawler`, `support-assistant` and `contract-insights`. The two apps change only because PR 65 added 5 lines to `graph/dynamodb/client.py`, which both zips bundle. Anything else is a stop.
- [x] **B3. Give the approval, then apply:**
  ```sh
  tofu apply -var schedule_state=ENABLED
  ```
  Always pass the variable, because a plain `tofu apply` sets the schedule back to `DISABLED`. Cost: $0, inside Always Free (ADR 0025). Undo the schedule by applying with `schedule_state=DISABLED`.
- [x] **B4. Recommended, needs its own approval: invoke `support-assistant` and `contract-insights` once each** (runbook L5, with the events in `tests/build/test_zip_handlers.py`). They have new code that has not run on AWS. Both must return. It adds about 2 small usage items and only calls the mocks. Done at 10:11 UTC on 2026-11-07: both returned 200, mock only.
- [x] **B5. Put the cron back.** Applied at 10:10:40 UTC on 2026-11-07 from `main`, with `-var schedule_state=ENABLED`. The plan was 0 add, 1 change, 0 destroy, changing only `schedule_expression`, and AWS then showed `ENABLED`, `cron(0 3 * * ? *)`, UTC.

## C. First scheduled run

- [x] **C1. After 03:00 UTC, confirm exactly one new run with `finished_at` set**, read from the table or the crawler's logs. The run was at 07:30 UTC under the temporary cron.
- [x] **C2. Note what it wrote.** Expected: three ChangeEvents, one per updated function, with new evidence for each. Other results are a reason to stop and check. Done: `resources_changed` was 3, with AFFECTS edges to `verity-crawler`, `support-assistant` and `contract-insights`.

## D. Close M3 and M8

- [x] **D1. Credits compared with $120.** The owner reported on 2026-11-07, at about 11:05 UTC, that no credit changed. That is **before** the 24-hour mark of 10:12 UTC on 2026-11-08 ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 3), so it is recorded as an owner-accepted exception (decision 5). A read at or after that time is recommended and would make it a full L17. Never use `aws ce`, which charges per request.
- [x] **D2. Record L15 and L17.** ADR 0032 is Accepted, with the early report and the exception in decision 5.
- [x] **D3. Mark M3 and M8 ✅** in Stage 4 and `docs/open-milestones.md`. Done through this PR.

## E. Create the live snapshot (closes M9)

Needs A2 merged and M8 ✅. A dry run on 2026-11-06 worked: read-only, clean scan, about 32 seconds. That file was a rehearsal and was deleted.

- [x] **E1. Prepare:**
  ```sh
  git switch main && git pull --ff-only
  git status            # must be clean
  export AWS_PROFILE=verity
  aws login
  ```
- [x] **E2. Give the approval, then assess.** This writes to AWS. It took 41 minutes last time, so start well clear of 03:00 UTC:
  ```sh
  uv run verity assess --target dynamodb
  ```
  Type the confirmation word and do not use `--yes`. Expect about 29 high findings. A different count is a stop. On 2026-11-07 the owner waived `--yes` for this one run: 29 high, 4 records, 29 minutes (ADR 0033).
- [x] **E3. Export and scan.** This only reads from AWS:
  ```sh
  git switch -c feat/m9-live-snapshot
  uv run verity export --out web/public/data/snapshot.json
  uv run verity export --check web/public/data/snapshot.json --require-live
  ```
  Expect 0 scan hits. A stale-graph refusal means repeat E2. A scan hit is a stop.
- [x] **E4. Do not commit yet. Switch to Opus** (`/model opus`) and ask it to review the redaction in `web/public/data/snapshot.json`. Point it at the ChangeEvents, which have never appeared in a live export.
- [x] **E5. Commit the file and open a PR:** the owner asked for one PR, so the docs for this step are in it as a separate commit.
  ```sh
  git add web/public/data/snapshot.json
  git commit -m "feat(web): publish the first live snapshot"
  git push -u origin feat/m9-live-snapshot
  gh pr create --fill
  ```
  Replace the PR text with the template, and wait for CI.
- [x] **E6. Merge it.** This is the owner's final confirmation, because a commit to a public repository cannot be taken back. Merging starts the Pages deploy. (PR 72, merged 2026-11-07.)

## F. Check the Pages URL (closes M10)

- [x] **F1. Confirm the deploy really ran:** `gh run list --workflow Pages --limit 1`, then open the run. The `deploy` job must have run and passed. A green run with `deploy` skipped proves nothing. (Runs 42373401481 and 42376760265: `build` and `deploy` both passed.)
- [x] **F2. Open <https://rohpod.github.io/verity/>** and hard-refresh with Cmd+Shift+R.
- [x] **F3. Check at desktop width:**
  - [x] Every page shows `data source: live` and a timestamp matching the export, with no "Recorded fixture" banner
  - [x] Overview, AI Registry, Risk register, Crosswalk and Controls load with provenance badges
  - [x] Support Assistant → controls & evidence, and Controls → VC-060, show the failure and the boundary note
  - [x] Graph explorer draws, and its lists label records, including Synthetic
  - [x] "What in this snapshot is not real" opens and lists the simulated components
- [x] **F4. Repeat at phone width** (390 px): nothing scrolls sideways, and the graph is a list. The first check found the Graph page 399 px wide; PR 73 fixed it and the re-check passed.
- [x] **F5. Paste a page's URL into a new tab** to confirm direct links work.

## G. Close M9 and M10

- [x] **G1. Mark M9 and M10 ✅** in Stage 4 and `docs/open-milestones.md`, with an M10 close-out and the demo link in the README. Done in the M11 close PR.

## H. M11: stage close

Starts when M8, M9 and M10 are ✅. Steps match the [plan](m10-m11-plan.md).

- [ ] **H1.** Close register, confirmed by Opus (step 1). Sonnet's draft arrives in A1
- [x] **H2.** `credential_process` fix and the CLI's "while it throttles" message (step 2). The message is fixed; the `credential_process` fix is deferred ([ADR 0034](adr/0034-m11-close-decisions.md) decision 9)
- [x] **H3.** Opus decides the open notes (step 3). The decisions are in [ADR 0034](adr/0034-m11-close-decisions.md), and Opus confirms them in the final review:
  - [x] Bedrock's 8 other `Invoke*` actions in `ai_signals.yaml`: deferred, decision 1
  - [x] Risk treatment decisions: build them, or drop them from ADR 0008: dropped from scope, decision 2
  - [x] Three obligation dates that no rule reads: stay as data, deferred, decision 3
  - [x] Art. 4a and the bias-test control: deferred, no content change, decision 4
  - [x] D15's overstated reason: corrected in the ADR, decision 5
  - [x] Re-seed pruning, and how long a re-seed takes: deferred, decision 6
- [x] **H4.** README real-vs-simulated table matches what was built (step 4). Done in the M11 close PR
- [ ] **H5.** Opus security review (step 5), including the 7 moderate `npm audit` advisories in dev tooling
- [ ] **H6.** Opus ADR review against the code (step 6)
- [x] **H7.** Final snapshot runbook (step 7). Now marked as the runbook for an optional refresh
- [x] **H8.** Final snapshot (step 8). The snapshot from PR 72 (`as_of` 2026-11-07T12:20:39.767Z) is the final one unless the owner asks for a refresh ([ADR 0034](adr/0034-m11-close-decisions.md) decision 11). A refresh needs the owner's approval, and it would first confirm the schedule is still `ENABLED`, re-verify EU AI Act dates, and run an assess. Hard deadline for any last snapshot: 1 Apr 2027
- [x] **H9.** Teardown plan (step 9). Keep the estate until after submission, then `tofu destroy` in the second half of April 2027, before the plan ends on 4 May 2027. This permanently deletes the table, and the committed snapshot stays as the record ([ADR 0034](adr/0034-m11-close-decisions.md) decision 12). The destroy still needs the owner's approval then
- [ ] **H10.** M11 validation, then mark it ✅ (step 10)

## Accepted limits (not pending)

These stay as they are, and do not block closing:

- Nobody has shown that the boundary stops a real Bedrock call, because a live call is forbidden. IAM's simulator is the accepted evidence (ADR 0028).
- CloudTrail event history cannot show SageMaker's invoke calls.
- Listed fields and scan rules cannot prove nothing sensitive exists beyond them, which is why Opus reviews the file (ADR 0030).
- The production smoke test uses a small static server, so GitHub Pages itself is proved only by section F.
- The main JS chunk is about 820 kB. It works, and it is not optimised.

## Stop and switch to Opus if

- The `tofu plan` differs from B2, or touches `module.table` or `module.guardrails`
- The high-finding count is not about 29, or any classification changes
- The scan reports a hit, or anything suggests a charge or that credits moved down
- A check fails after two fixes
