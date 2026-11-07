# 0035 — M11 final review: security, ADRs against the code, EU AI Act dates, and the stage close
- **Status:** Accepted (2026-11-07). Refines [0028](0028-m8-review.md) and [0033](0033-m9-live-snapshot.md); both stay in force. Confirms [0034](0034-m11-close-decisions.md). M11 is ✅ when this ADR's PR merges.

## Context
This is the end-of-stage review by Opus: checklist H1, H5, H6 and H10, and a re-check of the obligation dates. It made no AWS writes. With the owner's go-ahead it made read-only calls in eu-north-1 and ran `tofu plan`. Bedrock and OpenAI were not invoked. Every value below was measured on 2026-11-07, from about 14:13 UTC, with `main` at `0548188`.

## Security review (H5)
| Area | Checked | Result |
|---|---|---|
| Drift | `tofu plan -var schedule_state=ENABLED` | No changes |
| Roles | All 9 | All carry `verity-function-boundary`. Each trusts only its own service, with no account principal |
| Policies | `infra/modules/estate/locals.tf` | `Resource: "*"` only on the crawler's list and read actions. App writes are `PutItem` limited by `dynamodb:LeadingKeys`. No `iam:PassRole` and no `lambda:GetFunction` |
| Function URL | `mock-openai` | `AWS_IAM`, no resource policy, no CORS |
| Anything that could cost money | Trails, auto-scaling, capacity, logs | 0 trails, 0 scalable targets, provisioned Standard table at 15/15 plus GSI1 at 10/10, which is 25/25. All 8 log groups keep 3 days |
| Published snapshot | The bytes on Pages | SHA-256 equal to the committed file. 0 scan hits. No account ID in the file or the JS |
| Workflows | `pages.yml`, `ci.yml` | `contents: read` at the top. `pages: write` and `id-token: write` only on the deploy job. No secrets, no AWS credentials, no `pull_request_target`, and `npm ci --ignore-scripts` |
| Browser | Content-Security-Policy | `default-src 'self'` and `connect-src 'self'`. `style-src` allows `unsafe-inline` |
| Git history | All branches | No real account ID, no key, no real Function URL. Test data uses `abc123` hosts and AWS's example key. No state, tfvars or zip is tracked |
| JS dependencies | `npm audit` | 7 moderate, all dev tooling. `--omit=dev` finds 0 |
| Python dependencies | `pip-audit` on the locked packages | No known vulnerabilities. The two local packages were skipped |

Three low findings are accepted, and none blocks the close:
1. **Commit metadata holds the owner's personal email address** on nearly every commit. It is the owner's own, and it is not in any tracked file. Rewriting a public history would break every PR link, so it stays. The owner can use GitHub's noreply address from now on.
2. **Actions are pinned by version tag, not by commit SHA.** Dependabot watches them. The deploy job is the only one with write scopes.
3. **`unsafe-inline` in `style-src`, and no `frame-ancestors`,** which a meta tag cannot set. The site is static, with no login and no form.

## ADRs against the code (H6)
| Claim | Result |
|---|---|
| The summary fields in [0032](0032-m8-scheduled-run.md) and [0033](0033-m9-live-snapshot.md) | All 12 match `pipeline.py`. The log line matches `crawler/handler.py` |
| The three ChangeEvents | Read from the table on 2026-11-07, and they are in the published snapshot with their `AFFECTS` edges to the three functions. Config hashes are withheld |
| [0025](0025-m8-deploy-and-crawl.md) decisions 1, 7 and 8 | 256 MB, 300 s, the boundary's three deny patterns, no retries on either side, 3-day logs |
| `LIVE_TIME_NOTE` against [0028](0028-m8-review.md) and [0033](0033-m9-live-snapshot.md) | "can start a credential refresh" matches 0028, and "can" stays inside 0033's "not measured". Two mismatches are in decision 5 |
| Claims that the schedule runs daily | None. Each "daily" names the configuration, a design or a future rule |

## EU AI Act dates
All 7 entries in `content/rules/obligation_dates.yaml` were compared with the English HTML of Regulation (EU) 2026/1744 on EUR-Lex. No date changes.

| Entry | Date | Basis |
|---|---|---|
| `euaia-chapters-1-2` | 2025-02-02 | Art. 113, third paragraph, point (a), as amended |
| `euaia-omnibus-in-force` | 2026-07-27 | Published 24.7.2026, in force on the third day (Art. 4 of the amending act) |
| `euaia-general` | 2026-08-02 | Recital (40) of 2026/1744 only. Art. 113 of 2024/1689 itself could not be read |
| `euaia-art5-new` | 2026-12-02 | Art. 113, third paragraph, point (a), as amended |
| `euaia-art50-2-legacy` | 2026-12-02 | Art. 111(4), as amended |
| `euaia-high-risk-annex-iii` | 2027-12-02 | Art. 113, third paragraph, point (c)(i), as amended |
| `euaia-high-risk-annex-i` | 2028-08-02 | Art. 113, third paragraph, point (c)(ii), as amended |

Recital (1) of 2026/1744 says all rules apply "by 2 August 2027". That describes the original schedule, and the amended Art. 113 is what counts. The same text confirms that Art. 10(5) is deleted, that a new Art. 4a takes its place, and that Art. 4 is replaced.

`last_verified` stays 2026-11-05. Changing it would make the file differ from the published snapshot for no gain, and this ADR is the record of the re-check.

## Decision
1. **ADR 0034 is Accepted, with corrections made while it was still Proposed.** Decision 9 said the `credential_process` fix "would touch" zip code. The likely place is `graph/dynamodb/client.py`, which is in the zips, but a fix could sit outside it. Decision 11 and two later lines said the 2 Dec dates change a later export: only `euaia-art50-2-legacy` can, as the next decision explains. Its Consequences now point here for the dates.
2. **Only `euaia-art50-2-legacy` can change a later export.** `content/rules/applicability.yaml` reads it as a `legacy_date`, and no rule reads `euaia-art5-new`, as N32 already says. [0033](0033-m9-live-snapshot.md) names both, and that line is corrected here. The checklist, the plan and the runbook are fixed.
3. **M3 and M8 stay closed, and the 8 Nov read is not a condition.** [0032](0032-m8-scheduled-run.md) decision 5 is honest: it says the rule was not met and that credits can lag. Every ✅ now carries the exception. This review would have kept them open under CLAUDE.md's rule that a milestone waits for its criteria, but the owner may waive that and did so on the record. The read stays recommended, and credits below $120 reopen both.
4. **A correction to [0028](0028-m8-review.md).** Its decision 2 says live crawls ran against "the 120 s limit". The crawler's timeout is 300 s ([0025](0025-m8-deploy-and-crawl.md), `lambda.tf`, and the live config). No 120 s limit was found. The point stands: crawls took 14 to 22 s.
5. **The CLI note stays as it is, with two known mismatches.** On `verity assess` it says "than the estimate", though that command estimates writes, not time. And the 29-minute assess shows the time can be far more than "several times". Neither misleads a reader into harm, and a change is not worth another code PR now.
6. **One comment is corrected.** `locals.tf` said the boundary "makes this grant ineffective", which [0028](0028-m8-review.md) decision 5 says not to claim as fact. It now says what the simulator showed. A comment does not change the plan or any zip.
7. **M11 validation passes.** All 50 register rows are closed, deferred, dropped or standing, and each is confirmed. Rows were read against their cited source, with the decisive ones checked against the code; rows closed by an accepted ADR rest on that ADR. The README's real-vs-simulated table matches what was built. Every ❓ in Stage 2 and in the ADRs has a row.

## Alternatives
| Option | Why not chosen |
|---|---|
| Hold M11 for the 03:00 UTC run or the 8 Nov read | The owner chose not to wait. Neither is an M11 criterion, and both are recorded as not proved |
| Update `last_verified` | It changes a content file for no gain, and 2026-11-05 stays true |
| Rewrite history to remove the email | It breaks PR links and forks of a public repository |
| Fix the CLI note now | It is cosmetic, and `core/` changes redeploy Pages |
| Edit 0028 or 0033 | Accepted ADRs are not edited |

## Consequences
- **M0 to M11 are ✅ on merge,** with M3 and M8 by the owner's exception.
- **Not proved:** a run on `cron(0 3 * * ? *)`, a credit read at or after 10:12 UTC on 2026-11-08, and that the boundary stops a real Bedrock call ([0028](0028-m8-review.md) decision 5). The docs must not say the schedule runs daily until a run is checked.
- **For the owner:** the optional credit read, the optional refresh by 1 Apr 2027, and the teardown in the second half of April 2027, before 4 May 2027. The teardown needs approval then.
- **`euaia-general` rests on a recital,** because Art. 113 of 2024/1689 could not be read in this review.
