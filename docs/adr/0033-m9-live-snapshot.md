# 0033 — M9 live snapshot: what the first live export measured, and what it was built without
- **Status:** Accepted (2026-11-07). Refines [0029](0029-m9-snapshot-export.md), [0030](0030-m9-redaction-review.md) and [0032](0032-m8-scheduled-run.md); all stay in force. M9 closes when the owner merges this file's PR. M10 stays open until the Pages URL is checked.

## Context
[0029](0029-m9-snapshot-export.md) decision 13 held the snapshot until M8 closed, and [0032](0032-m8-scheduled-run.md) closed M8 on an early report. Every result so far came from the fixture and hand-built graphs. This is the first export from the live table. Every value below was measured on 2026-11-07 in eu-north-1. Bedrock and OpenAI were not invoked, and the snapshot labels them as simulated.

## Results
| # | Step | Measured | Expected | Held? |
|---|---|---|---|---|
| E1 | Preconditions | `main` at `8fee64d`, clean. Schedule `ENABLED`, `cron(0 3 * * ? *)`. Nothing in `core/`, `sdk/`, `apps/`, `mocks/`, `crawler/`, `content/`, `infra/`, `scripts/` or `uv.lock` changed since the deployed `756cc60` | As stated | Yes |
| E2 | Estimate before writing | 4 records, 0 new assessments, about 16 write units | Small: only 5 Evidence items changed | Yes |
| E2 | `verity assess --target dynamodb --yes` | **29 minutes** (11:51 to 12:20 UTC). Wrote 2 assessment edges and closed 2. A second estimate gave 0 records | 29 high | Yes: **29 high**, 406 medium, 2 low |
| E3 | `verity export` | 673 nodes, 1,325 edges, 437 findings, 928 requirement statuses, 1,072 obligations, 42 crosswalk rows. `as_of` 2026-11-07T12:20:39.767Z, `data_source: live`. 1,344,918 bytes | Under the limit | Yes |
| E3 | Redaction report | Own account replaced, 0 other accounts, 21 hash keys and 1 tag withheld, 21 Evidence rebuilt, 10 unchanged | As designed | Yes |
| E3 | `verity export --check --require-live` | **0 scan hits** | 0 | Yes |
| E4 | Opus review, separate from the scanner | See below | Nothing sensitive | Yes |
| E4 | Web checks with the snapshot in `web/public/data/` | 93 tests, lint, build and `check:dist` pass | All pass | Yes |

## The redaction review
The check compared the file with the real values, taken from AWS and the state file, and printed only counts and paths.

| Check | Result |
|---|---|
| Real account ID, plain or grouped | Absent |
| Function URL and its host | Absent |
| All 31 ARNs in the state file | Absent. The 29 `arn:aws` strings all carry `000000000000` |
| Env values | Only env names are published. 9 values were compared: the text of four also appears for unrelated reasons (the log level, the public table name, `mock-bedrock`, the tenant `kestrel`). None comes from an env value |
| Identity strings | No owner name, email, local path or AWS key ID. 0 email addresses |
| `amazonaws.com` | 9, all service principals in role trust policies (`lambda`, `scheduler`) |
| ChangeEvents, first time in a live export | 3, with `AFFECTS` edges to `verity-crawler`, `contract-insights` and `support-assistant`. `previous_config_hash` and `new_config_hash` are withheld |
| Other 12-digit values | Only the `000000000000` placeholder and parts of hashes |
| People | All 15 Persons are `synthetic` |
| Commit SHAs | 5 decisions, none null |

`code_sha256` stays in the config evidence. It is a hash of a zip built from this public repository, and it is what shows the three changed functions changed.

## Decision
1. **The snapshot is safe to publish, subject to the owner's merge.** The scan and the review agree. A commit to a public repository cannot be taken back, so merging is the owner's final confirmation.
2. **The owner waived the checklist's "do not use `--yes`" for this one assess.** The prompt needs a terminal, so it cannot be answered from an agent session. The owner saw the estimate, the price and the undo, and chose the flag. The rule stands for later runs.
3. **The snapshot was built without two things, by the owner's decision.** No run on `cron(0 3 * * ? *)` was checked, and no credit read at or after 10:12 UTC on 2026-11-08 was taken. The owner chose not to wait, assuming credits stay at $120, and will report any change. Neither is a criterion of M9, and [0032](0032-m8-scheduled-run.md) decision 5 says nothing waits on the read. Docs still must not say the schedule runs daily. If credits fall below $120, M3 and M8 reopen. The published file would not need to change for that.
4. **The time of an assess follows the table, not the writes.** 4 records took 29 minutes, and the rehearsal that stopped before writing took 30 seconds. `apply_assessment` reads and compares far more than it writes. The credentials were in their refresh window for part of the run ([0028](0028-m8-review.md)), which probably explains much of it, but this was not measured.
5. **A correction to [0032](0032-m8-scheduled-run.md).** Its Context says values came from read-only calls. The cron revert and the B4 invokes were writes, and the 0, 4, 0 plan for L15 was the owner's report. The values stand. Its title says the credit read waits for 8 Nov, while decision 5 closed M3 and M8 without waiting; decision 5 is what happened.

## Alternatives
| Option | Why not chosen |
|---|---|
| Wait for the 03:00 UTC run and the credit read | The owner chose not to wait: neither is an M9 criterion |
| The owner runs the assess in a terminal | It needed the owner at a terminal for about 30 minutes, for 4 records |
| Rely on the scanner alone | [0030](0030-m9-redaction-review.md) keeps a human-level review as the last check, because rules cannot prove nothing else exists |
| Withhold `code_sha256` | It reveals nothing beyond the public source, and removing it would hide why the ChangeEvents exist |
| Separate PRs for the snapshot and the docs | The owner asked for one PR. Only the snapshot file changes what is published |

## Consequences
- **M9 closes on merge.** Its three criteria pass on live data, and the Pages deploy runs for the first time. M10 needs the Pages check in section F.
- **Not proved:** a Pages deploy, a run on the 03:00 cron, and a credit read after the 24-hour mark.
- **The snapshot goes out of date.** `euaia-art50-2-legacy` and `euaia-art5-new` take effect on 2 Dec 2026, and crawls renew evidence from about 29 Nov, so a later export needs a fresh assess. The final snapshot is still due by 1 Apr 2027.
- **Known limit, unchanged:** the listed fields, the scan and this review cannot prove that nothing sensitive exists beyond them ([0030](0030-m9-redaction-review.md)).
