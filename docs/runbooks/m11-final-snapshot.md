# Runbook: M11 final snapshot

**For an optional refresh only.** The snapshot from PR 72 (`as_of` 2026-11-07T12:20:39.767Z) is the final one unless the owner asks for a refresh ([ADR 0034](../adr/0034-m11-close-decisions.md) decision 11). This is the runbook for that refresh, step 8 of the [M10 and M11 plan](../m10-m11-plan.md). If one is made, **start by 15 Mar 2027, for a hard deadline of 1 Apr 2027.** The Free plan ends on 4 May 2027.

**Status: tested once.** Written by Sonnet on 2026-11-07, before the first live run. Since then the first live export ran and was reviewed ([ADR 0033](../adr/0033-m9-live-snapshot.md)), one scheduled crawl has happened ([ADR 0032](../adr/0032-m8-scheduled-run.md)), and the Pages deploy ran and the live site was checked ([ADR 0034](../adr/0034-m11-close-decisions.md)). Steps still marked **(unverified)** have not been run. Opus should re-read this runbook against those results before a refresh.

Every step marked **APPROVE** needs the owner's yes for that step, at that moment, with what it does, the verified price and how to undo it. Approval of one step never covers the next. Stop at the first surprise and record every measured value as you go.

Run everything with `export AWS_PROFILE=verity`. Never paste an account ID, ARN, Function URL or email into the repo, a PR or an ADR. Never make a Bedrock or SageMaker call, even one expected to be refused: Bedrock and OpenAI stay mock-only. Only one writer at a time ([ADR 0014](../adr/0014-m2-measurements-and-evidence-cap.md)): never run a seed and a crawl together, and keep a manual crawl well away from the schedule's 03:00 UTC run.

## Before you start

All of these must be true. If one is not, stop.

| # | Condition | Source |
|---|---|---|
| P1 | M8, M9 and M10 are ✅. That means the L15 scheduled run was checked, the owner's credit read matched, a first live snapshot was reviewed and merged, and the Pages URL worked | [Plan](../m10-m11-plan.md), track F |
| P2 | `main` is current, `git status` is empty, and CI is green on `main` | [CONTRIBUTING](../../CONTRIBUTING.md) |
| P3 | Opus has re-verified the EU AI Act obligation dates and every `last_verified` value (S1), and any change is merged | Plan, "Before the final snapshot" |
| P4 | The M11 close register in [Stage 4](../stage-4-milestones.md#m11-close-register-draft) has no row that would change what the file shows | Plan, step 1 |

## Steps

| # | Step | Command or action | Expected | Undo |
|---|---|---|---|---|
| S0 | Check the window and the tree | `date`, then `git switch main`, `git pull --ff-only`, `git status` | On or before 15 Mar 2027 to start, and never after 1 Apr 2027. Empty `git status` | n/a |
| S1 | **Opus:** re-verify the dates | Read `content/rules/obligation_dates.yaml`: each date's `source_url` and `last_verified`. The law may have changed since | Unchanged, or a PR by Opus that updates them first. Dates are data, never hard-coded (CLAUDE.md). Do not change one in this task | n/a |
| S2 | **Owner** reads credits in the Billing console | Not `aws ce`: Cost Explorer charges per request | Baseline recorded | n/a |
| S3 | Check the schedule is still on | `aws scheduler get-schedule --name verity-crawl-daily` (the schedule is in the `default` group) | `State` is `ENABLED`. A plain `tofu apply` resets it to `DISABLED` ([ADR 0028](../adr/0028-m8-review.md)). If it is `DISABLED`: stop. Turning it on is an APPROVE step, `cd infra && tofu apply -var schedule_state=ENABLED`, after a `tofu plan` the owner has read in full | Apply with `DISABLED` |
| S4 | Decide whether a crawl is needed | Crawler evidence lasts 30 days and is renewed about every 22 days, and only a crawl renews it (plan). Look at the date of the newest `DiscoveryRun` **(unverified: no command is written for this yet)** | Evidence younger than about 22 days: skip S5. Otherwise run S5 | n/a |
| S5 | APPROVE: crawl now, if S4 says so | `uv run verity crawl` (invokes the deployed crawler once; it reads the account and writes the graph) | Counts printed, `crawl wrote:` line. Not between 02:50 and 03:10 UTC. The crawl took 17 to 22 s in M8 | n/a (the records are the point) |
| S6 | APPROVE: assess | `uv run verity assess --target dynamodb` | Required after any crawl that wrote evidence, or the export refuses a stale graph. It took 41 minutes in M8 and 29 minutes for 4 records in M9 ([ADR 0033](../adr/0033-m9-live-snapshot.md)), so plan on its time whatever the estimate says. It may be faster if the `credential_process` fix has landed **(unverified)**. Do not start a second one | n/a |
| S7 | Export | `uv run verity export --out .build/snapshot.json` | `data source: live graph, read-only`, counts, `redaction:` line, `scan: clean`. Under 2 MiB (about 1.5 MiB is the estimate, ADR 0030). `.build/` is ignored by git. For a refusal, see "What a refusal means" | Delete `.build/snapshot.json` |
| S8 | Scan the file again, on its own | `uv run verity export --check .build/snapshot.json --require-live` | `0 scan hit(s)`, and it is a live file. The scan is read-only | n/a |
| S9 | Compare with the last published snapshot | `git diff --no-index --stat web/public/data/snapshot.json .build/snapshot.json` | Differences are explained by: new crawl evidence, evidence that aged, new ChangeEvents, and the date changes below. Anything else goes to Opus | n/a |
| S10 | Branch and place the file | `git switch -c chore/m11-final-snapshot` from an updated `main`, then copy `.build/snapshot.json` to `web/public/data/snapshot.json` | Only that one file changes | `git restore` the file |
| S11 | Check the build with the file in place | `npm ci --ignore-scripts --prefix web`, `npm run build --prefix web`, `npm run check:dist --prefix web` | The build passes and `dist/` has no snapshot of its own ( `copyPublicDir` is off). The Pages workflow adds the file and scans those exact bytes | n/a |
| S12 | **Opus** reviews the redaction | See "Review before commit". A commit to a public repository cannot be taken back | Written sign-off in the PR | Do not merge |
| S13 | Open the PR | Template, Conventional Commit (`chore(data): publish the final snapshot`), no attribution lines. Switch back to `main` and ask the owner to merge | The owner reviews and merges on GitHub. Never merge it yourself | Close the PR |
| S14 | Watch the Pages workflow | GitHub Actions, workflow `Pages` | The build job scans with `--require-live`, then the deploy job runs. The first real deploy ran on 2026-11-07 and passed (runs 42373401481 and 42376760265) | Revert the merge |
| S15 | Check the Pages URL | Desktop and phone width, every route, a deep link, the timestamp | The timestamp is the new `as_of`. No fixture banner. `header.simulated_components` is reachable | n/a |
| S16 | **Owner** reads credits at least 24 hours after the latest one-off change; daily crawls do not restart the wait ([ADR 0032](../adr/0032-m8-scheduled-run.md), decision 3) | Billing console | Unchanged ([ADR 0015](../adr/0015-account-baseline.md): credits can lag) | n/a |
| S17 | Record the results | A new ADR. Accepted ADRs are not edited | Measured times, sizes, the diff summary and anything surprising | n/a |

## Differences to expect

- **2 Dec 2026.** `euaia-art50-2-legacy` and `euaia-art5-new` take effect, so a later snapshot can differ from an earlier one in applicability and status. Review the difference. Do not assume it is a fault, and do not adjust it ([plan](../m10-m11-plan.md)).
- **Evidence ages.** Each crawl renews evidence about every 22 days. Freshness values, and the findings that depend on them, move with it.
- **Code changes.** A deployed function whose code changed produces a ChangeEvent on the next crawl ([open milestones](../open-milestones.md)).
- **New decision commits.** `decision_commits` gains an entry for each decision file merged since the last snapshot.

## What a refusal means

| Message | Meaning | What to do |
|---|---|---|
| `an assessment would still write ...: run verity assess first` | The stored assessments are not the ones an assessment now would produce (usually a crawl wrote new evidence) | Run S6, then S7 |
| `no commit holds the recorded file for N decision(s): ...` | A decision file in the graph has no commit with that content in git history | Fix the checkout: commit or restore the file, or seed from the committed content. Do not edit the lookup. If unclear, Opus |
| `the table is empty` | Wrong table or tenant, or nothing was seeded | Stop and ask. Do not seed to make it pass |
| `scan hit: <category> at <path>` | The scanner found an account ID, digest, Function URL, email, canary, identity or path, key ID or an old hash | **Stop. Nothing was written.** Do not edit the scanner or the field lists to pass. Opus |
| `refused: N bytes is over ...` (size) | The file is over 2 MiB | Stop. Opus decides whether the limit or the content changes |
| `cannot build the snapshot: <ErrorType>` | Only the type is printed. `ClientError`, `EndpointConnectionError` or `NoCredentialsError` is an AWS or connection problem. `ValueError` can also mean the graph does not show the owner's account, or two accounts appear in function roles ([ADR 0030](../adr/0030-m9-redaction-review.md), decision 7) | For an AWS type: check credentials (`aws login`) and the network, then try again. For `ValueError`, or if it persists: stop. Opus |

## Review before commit

For Opus, before the owner merges. The scanner has a last word on patterns, but the listed fields and rules cannot prove that nothing sensitive exists beyond them. Free text from reviewed YAML (requirement summaries, decision statements, names, `purpose`) is only scanned ([ADR 0030](../adr/0030-m9-redaction-review.md)).

- `header.data_source` is `live`, `schema_version` is 1, and `as_of` is the run's time, not the start of a day.
- `header.redaction` counts look right: the own account replaced, no other accounts, Evidence rebuilt, tags and content keys withheld.
- `header.simulated_components` still names what is not real, including the simulated providers and sign-offs.
- `S8` was clean, and the PR's CI check (`--require-live`) passes.
- Search the file by eye for: an account-like number, `lambda-url`, `.on.aws`, `@`, `/Users/`, a name that is not in the invented cast, and any environment variable value.
- Every `commit_sha` is 40 hex digits and is reachable in the public repository's history.
- The size is about what was estimated, and nothing under `web/public/data/` other than the one file changed.

## Stop and switch to Opus

Stop and tell the owner to switch to Opus if: any scan hit; a refusal this runbook does not explain; a date, a `last_verified` value or any wording about regulation looks different from the last snapshot; the diff holds something S9 does not explain; the schedule is `DISABLED`; an apply or crawl behaves differently from M8; a charge or a credit move appears; IAM needs to change; or the same problem survives two fixes.

## After this runbook

Teardown is **not** part of it. It is decided in [ADR 0034](../adr/0034-m11-close-decisions.md) decision 12: keep the estate until after submission, then run `tofu destroy` in the second half of April 2027, before the plan ends on 4 May 2027. That permanently deletes the table, and the published snapshot becomes the only record. The plan must never be upgraded. The destroy needs the owner's approval then.

## Not known yet

- How long the assess takes after a `credential_process` fix. The fix is deferred ([ADR 0034](../adr/0034-m11-close-decisions.md) decision 9), so expect a slow assess (29 minutes for 4 records in ADR 0033).
- The command to read the newest `DiscoveryRun` (S4).
- The first live file was 1,344,918 bytes (ADR 0033); check a later one against the 1.5 MiB estimate.
- What the 2 Dec 2026 date changes do to the file. The three ChangeEvents from L15 happened on 2026-11-07 ([ADR 0032](../adr/0032-m8-scheduled-run.md)) and appeared in the live export with their hashes withheld ([ADR 0033](../adr/0033-m9-live-snapshot.md)).
