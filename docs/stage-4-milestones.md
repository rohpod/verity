# Stage 4 — Milestone plan

_2026-11-05 · Approved. Status key: ⬜ not started · 🔄 in progress · ✅ validated._
Inputs: [architecture](architecture.md) · [ADRs](adr/) · [why M3, M8 and M9 are open](open-milestones.md) · [M10 and M11 plan](m10-m11-plan.md). Decisions by the owner: mock-openai uses an `AWS_IAM` Function URL ([ADR 0009](adr/0009-mock-openai-iam-auth.md)); milestones run AWS first, UI last.

## Findings from read-only checks (2026-11-05)

| Finding | Effect |
|---|---|
| Plan expires **4 May 2027**; $100 credits left; no Lambda functions or DynamoDB tables in eu-west-1 | Take the last live snapshot by **1 Apr 2027** |
| Lambda account concurrency is **10**; AWS requires 100 to stay unreserved | Reserved concurrency can't be set; dropped ([ADR 0009](adr/0009-mock-openai-iam-auth.md)) |
| `ListFunctions` returns env var values | IAM can't enforce "names only"; the crawler discards values on receipt (D1) |
| CLI session is **root**; default region is **ap-south-1** | **Updated:** the CLI now uses IAM user `rohpod` in **eu-north-1** ([ADR 0011](adr/0011-region-eu-north-1.md)). M3 granted its permissions ([ADR 0015](adr/0015-account-baseline.md)) |
| `python3.12` supports arm64; deprecation forecast 31 Oct 2028 | Closes the architecture §B ❓ |
| `aws login` flow works | Closes the architecture §J ❓ |
| `tofu` 1.13.5 installed, `terraform` not; repo is public; `gh` logged out | Use `tofu`; owner runs `! gh auth login` |
| Function URL pricing unconfirmed | **Confirmed:** no extra charge ([ADR 0025](adr/0025-m8-deploy-and-crawl.md)) |

## Design clarifications

| # | Resolution |
|---|---|
| D1 | Env var values are discarded at the collector boundary; never stored or logged. A canary value is tested across graph, logs and snapshot |
| D2–D6 | See [ADR 0010](adr/0010-assessment-and-crosswalk-semantics.md) |
| D7 | `GraphRepository` gains `append_usage`, `usage_records` and `close_edge` |
| D8 | Adapters take a narrow `UsageSink` from the graph package; app roles are limited to their own partition with `dynamodb:LeadingKeys` |
| D9 | `verity attest` only scaffolds a YAML file under `content/decisions/` (ADR 0008 requires a reviewed PR) |
| D10 | Export keeps the commit SHA only, and fails if any email address is found |
| D11 | Demo L4 sign-offs are labelled *simulated sign-off* in data and UI |
| D12 | One `source` → badge mapping, with a Simulated badge added |
| D13 | Provider-scoped inheritance resolves system → model → provider; in-house models resolve to Not applicable |
| D14 | GSI projects keys only; `H#` written only on real change; writes retry with backoff; inline evidence cap is 16 KB, provisional until M6 ([ADR 0014](adr/0014-m2-measurements-and-evidence-cap.md)) |
| D15 | All 18 node types are kept, because the §L traversals need them |
| D16 | Schema refinements found while planning M1. See [ADR 0012](adr/0012-graph-schema-refinements.md) |
| D17 | How `DynamoDBRepository` writes and reads. See [ADR 0013](adr/0013-dynamodb-write-model.md) |
| D18 | M2's results: throttling retries, measured costs and the evidence cap. See [ADR 0014](adr/0014-m2-measurements-and-evidence-cap.md) |
| D19 | How the account is set up and guarded. See [ADR 0015](adr/0015-account-baseline.md) |
| D20 | What the real table showed. See [ADR 0016](adr/0016-m3-live-results.md) |
| D21 | Mapping direction, strength, `sufficiency: full`, obligation dates and ISO provenance. See [ADR 0017](adr/0017-m4-content-semantics.md) |
| D22 | Mappings from a text nobody read claim only an overlap, so ISO requirements never show as Satisfied. See [ADR 0018](adr/0018-unread-standards.md) |
| D23 | M5 rules: automated-only guardrail, Art. 111(2), high-risk candidates, decisions as Evidence, *Not met*. See [ADR 0019](adr/0019-m5-rules-and-assessment.md) |
| D24 | M5 review fixes: decision lifecycle, risk-tier expiry, unknown facts, severity from binding law, ended assessments. See [ADR 0020](adr/0020-m5-review-fixes.md) |
| D25 | M6 discovery: evidence on change only, summarised over the cap, one cleaning boundary, VC-060 for unused permissions, Candidate lifecycle. See [ADR 0021](adr/0021-m6-discovery.md) |
| D26 | M6 review fixes: concrete AI actions, an inconclusive VC-060 outcome, account digests, signal matching. See [ADR 0022](adr/0022-m6-review-fixes.md) |
| D27 | M7 demo estate: layered `verity_ai`, corrected crawl fixture, runtime refusal of real endpoints, pure-Python talent model, deterministic zips. See [ADR 0023](adr/0023-m7-demo-estate.md) |
| D28 | M7 review fixes: bounded telemetry, quiet AWS logs, a usage partition, reproducible zips, input ranges, a permissions boundary in M8. See [ADR 0024](adr/0024-m7-review-fixes.md) |
| D29 | M8 deploy: the crawler function, refused CloudTrail events prove nothing, simulator proof of the boundary, a real refused write, a fixture-shaped estate. See [ADR 0025](adr/0025-m8-deploy-and-crawl.md) |
| D30 | M8 cold start: bytecode in the zips that vendor packages, 512 MB for the apps that load pydantic and for the probe. See [ADR 0026](adr/0026-m8-cold-start.md) |
| D31 | M8 review: seed and assess time came from credential refreshes, the schedule and credit steps reworded, boundary claims matched to the evidence. See [ADR 0028](adr/0028-m8-review.md) |
| D32 | M9 export: listed public fields, rebuilt hashes for redacted Evidence, an independent fail-closed scanner, a generated contract. See [ADR 0029](adr/0029-m9-snapshot-export.md) |
| D33 | M9 redaction review: scan before writing, listed Evidence content and tags, a stricter scanner, a header that names what is not real. See [ADR 0030](adr/0030-m9-redaction-review.md) |
| D34 | M10 dashboard: one data path, no governance derived in the UI, a build that cannot carry a fixture. See [ADR 0031](adr/0031-m10-dashboard.md) |
| D35 | M8 scheduled run: L15 passed on a one-off cron that was reverted, and the L17 credit read comes at least 24 hours after the latest one-off change. See [ADR 0032](adr/0032-m8-scheduled-run.md) |
| D36 | M9 live snapshot: first live export measured and reviewed, built without a 03:00 UTC run or a late credit read, by the owner's decision. See [ADR 0033](adr/0033-m9-live-snapshot.md) |

## Milestones

| | Milestone | Lead | AWS mutation | Status |
|---|---|---|---|---|
| **Core engine (local)** | | | | |
| M0 | Foundations: uv workspace, ruff, pytest, CI without AWS credentials, Dependabot, mutating-command hook | Sonnet | no | ✅ |
| M1 | Graph core: models, IDs, `GraphRepository`, `InMemoryRepository`, NetworkX loader, traversals | Opus, then Sonnet | no | ✅ |
| M2 | `DynamoDBRepository` (moto), shared contract suite | Sonnet | no | ✅ |
| **AWS baseline** | | | | |
| M3 | Account baseline: non-root admin with MFA, region eu-north-1, `infra/` root, $0.01 budget, `verity-graph` | Opus (IAM), Sonnet | **yes, approval first** | ✅ (exception, [ADR 0032](adr/0032-m8-scheduled-run.md)) |
| **Governance logic (local)** | | | | |
| M4 | Content: hub controls, ~35 requirements, STRM mappings, Kestrel org, synthetic systems, `verity seed` | Sonnet builds the loader, linter, CLI and org data; Opus writes the regulatory content | no | ✅ |
| M5 | Rules and assessment: applicability, status, assurance, satisfaction, `verity assess`, `verity attest` | Opus, then Sonnet | no | ✅ |
| M6 | Discovery pipeline (8 stages), `ai_signals.yaml`, `verity crawl --local` | Sonnet | no | ✅ |
| M7 | Demo estate code: mocks, `verity_ai` with SigV4 hook, 5 apps, local talent model | Sonnet | no | ✅ |
| **Live** | | | | |
| M8 | Deploy and first live crawl: Lambda modules, schedule, SSM manifests, guardrails | Opus (IAM), Sonnet | **yes, approval per apply** | ✅ (exception, [ADR 0032](adr/0032-m8-scheduled-run.md)) |
| **Public demo** | | | | |
| M9 | Snapshot export, redaction, schema, generated TS types | Sonnet; Opus reviews redaction | no | ✅ on merge ([ADR 0033](adr/0033-m9-live-snapshot.md)) |
| M10 | Dashboard in three slices, GitHub Pages | Sonnet | no | 🔄 |
| M11 | Stage close: security review, ADR review, final snapshot by 1 Apr 2027, teardown decision | Opus | teardown/refresh only | ⬜ |

## Validation criteria

- **M0:** pytest and ruff pass locally and in CI; the hook blocks a sample `tofu apply`.
- **M1:** all 5 §E traversals pass for all 3 use cases as executable tests; invalid edges are rejected (for example `PROVIDED_BY` on an in-house model); D4 and D7 covered.
- **M2:** one contract suite passes on both repositories; re-upserting an unchanged node writes no `H#`; a test fails if boto3 DynamoDB is used outside the repository; D14 cap set from measured item sizes.
- **M3:** eu-north-1 re-checked first (no existing functions or tables; Lambda concurrency limit); session is no longer root; table is PROVISIONED, STANDARD, 15/15 + 10/10, no auto-scaling; a real repository round trip works; credits unchanged.
- **M4:** content linter passes (every requirement has `source_url`, `source_version`, `last_verified`; every mapping has a rationale); ISO entries hold IDs and original summaries only; no derived link has a STRM type; seeding twice changes nothing. STRM, EU AI Act dates and ISO 27001 Amendment 1 re-verified first.
- **M5:** date-boundary tests either side of every obligation date; role tests; property test that no automated input makes a non-automatable control Implemented; D2, D3, D13 cases; bias-test and DPA gaps appear as findings.
- **M6:** `shadow-summariser` scores *probable*, `invoice-renderer` *none*; D1 canary appears nowhere; `lambda:GetFunction` never called; re-crawl duplicates nothing except run and evidence records; a config change yields a ChangeEvent and stale evidence.
- **M7:** adapter shape tests pass; a test fails if a real Bedrock client appears anywhere; pure-Python inference matches training output; zips well under 50 MB; simulated components labelled.
- **M8:** Function URL pricing confirmed first; all 5 functions classify as expected; an unsigned call to mock-openai is refused; unused `bedrock:InvokeModel` finding appears and CloudTrail shows no Bedrock use; second crawl idempotent; destroying the estate then applying rebuilds it cleanly ([ADR 0025](adr/0025-m8-deploy-and-crawl.md)); credits unchanged.
- **M9:** scans of a snapshot built from live data find no account ID, Function URL host, env value or email; schema validates; every record has provenance and the file has its `as_of`.
- **M10:** typecheck and build pass; `snapshot.json` is the only data source; every view shows provenance and timestamp; works at phone width; Pages URL works.
- **M11:** every §L and ❓ item is closed or explicitly deferred; the README real-vs-simulated table matches what was built.

## M4 re-verification (2026-11-05)

The M4 criterion says STRM, EU AI Act dates and ISO 27001 Amendment 1 are re-verified first. Results:

| Item | Result | Source | Status |
|---|---|---|---|
| STRM types and rationales | The 5 types and 3 rationales match `enums.py`. Type and rationale "must be used together" | NIST IR 8477 final, February 2024, read in full | ✅ Closes the ADR 0004 ❓ |
| STRM strength | Not defined by NIST. The 1 to 10 scale is Secure Controls Framework practice | NIST IR 8477, full text | ⚠️ Corrected in [ADR 0017](adr/0017-m4-content-semantics.md) |
| STRM direction | "A subset of B" means B contains everything A does and more. Our documents never fixed which side is A | NIST IR 8477 | ⚠️ Fixed in ADR 0017 |
| EU AI Act dates | Read in the Official Journal: published 24 Jul 2026, in force 27 Jul 2026; 2 Dec 2027 (Annex III), 2 Aug 2028 (Annex I), 2 Dec 2026 (Art. 50(2), systems already on the market; Art. 5 additions). Art. 113 of the base text keeps 2 Aug 2026 as the general date, which includes Art. 50. All match Stage 2 | Regulation (EU) 2026/1744 and 2024/1689, read through the EU Publications Office, because EUR-Lex returned an empty page to automated fetches | ✅ |
| ISO/IEC 27001:2022 Amendment 1:2024 | "Climate action changes", February 2024. Adds to clauses 4.1 and 4.2. No sign of Annex A changes | Public preview of the amendment and a national adoption listing. iso.org returns 403 | ✅ Enough for our use, and recorded as `public_listing` |
| NIST AI RMF | 1.0 is still current. A revision is in progress with no public draft found | nist.gov | ✅ |
| ISO/IEC 42001 sub-control IDs | Two public listings agree on all 38 IDs. A third disagrees on many ([details](../content/README.md)) | Secondary only | ⚠️ Kept as `public_listing`, and limited by [ADR 0018](adr/0018-unread-standards.md) |

## M5 close-out (2026-11-06)

The end-of-milestone review reopened M5 until the fixes in [ADR 0020](adr/0020-m5-review-fixes.md) landed. Its experiments were then run again on a copy of the real content, after the fixes were merged:

| Experiment | Before | After |
|---|---|---|
| Correct a verification on the same day | The old decision won 10 of 60 times | The correction won 60 of 60 |
| Correct a risk tier on the same day | The old decision won 37 of 40 times | The correction won 40 of 40 |
| Delete a decision file | Nothing changed | Refused. A revocation removes the L4 and the *Satisfied* result |
| Expired `not_high_risk` decision, at 2028-01-01 | No Chapter III edges and no finding | 13 edges and a high `risk_tier_expired` |
| System with no `roles` or `use_domains` | No obligations and no finding | Two high `unknown_fact` findings |
| High findings on the real content | 427 high `no_evidence` | 27: 22 `no_evidence`, 4 `provider_unknown`, 1 `risk_tier_unconfirmed` |
| System leaves scope | Its assessments stayed open | 13 edges closed, 2 assessments ended, and a second run writes nothing |
| Attest for each of the 29 controls, unedited | `account_id_like` false positive on some | Lint stops on `decision_todo` only, plus `decision_scope_mismatch` where the scope is wrong |

The Talent Screening bias-test gap stays a high finding, and the mock OpenAI DPA gap (VC-050) is a medium one. Requirements resting on demo sign-offs are labelled simulated. The owner's review of `content/rules/applicability.yaml`, which ADR 0019 asks for, is recorded by approving the pull request that closes M5.

## M6 close-out (2026-11-06)

The end-of-milestone review reopened M6 until the fixes in [ADR 0022](adr/0022-m6-review-fixes.md) landed. Its experiments were then run again on merged `main`, on copies of the recorded fixture. Nothing was read from AWS.

| Experiment | Before | After |
|---|---|---|
| Role with `NotAction` (PowerUser shape) | VC-060 passed at L3 | Fails: 8 listed AI actions granted, 2 unused, 6 unverifiable |
| `bedrock:InvokeModel` used through `Converse` | Read as unused | Passes |
| Trust moved to another external account | No ChangeEvent | One ChangeEvent, and new snapshot and VC-060 Evidence |
| `LEGAL_OPENAI_API_KEY`, `AWS_BEDROCK_REGION`, `APP_ANTHROPIC_TOKEN`, `CHATGPT_KEY` | Scored none | Probable |
| `ContractSummariserFn`, `MyStack-OpenAiProxy-AB12` | Scored none | Possible |
| 12-digit number in a function, env var or role name | Stopped the crawl | Crawls cleanly, as an `acct_` digest |
| `DEBUG` logging during `collect` | Canary in the log | Canary absent |
| Crash at the evidence step, then retry | Failed check hidden as `no_evidence` for about 3 weeks | Evidence rewritten, `control_not_met` high, and the next crawl writes only the run |
| Function whose role the crawler cannot see | VC-060 passed on the rest | Inconclusive |
| Any tag on a function | Hid shadow AI | `shadow-summariser` stays a Candidate |
| `verity assess` on the day of a crawl | Ignored the crawl's evidence | Assesses as of now |

The original criteria also hold. `shadow-summariser` scores *probable* and `invoice-renderer` *none*. `lambda:GetFunction` is never called. A second crawl, even with every API list reordered or after a re-seed, writes only the run. A config change gives a ChangeEvent and stale evidence. The seeded `AISystem` facts are untouched. `verity crawl --local` gives 29 high findings, and `verity assess` alone 27.

Open for M8: the AI action list is checked against the IAM reference (below), because that page could not be read while building M6. The live path of the crawler has not run, and M6 proves it against `moto` and a stub only.

## M7 close-out (2026-11-06)

The end-of-milestone review reopened M7 until the fixes in [ADR 0024](adr/0024-m7-review-fixes.md) landed (#48). The re-review ran the review's experiments again on merged `main`, then added failure cases they had not covered, which found more gaps, fixed in #49. Everything ran from the built zips against a local fake with fake credentials. Nothing reached AWS.

| Experiment | Before | After |
|---|---|---|
| DynamoDB throttled on `support-assistant` | Held the handler 37.1 s, past the 10 s timeout | Returns in about 1 s, 2 attempts, `usage_write_failed` logged |
| `LOG_LEVEL=DEBUG`, root logger forced to `DEBUG` | Customer message and session token in the log | Nothing on stderr. A control run with the fix undone shows both canaries, so the check can fail |
| Usage record location | In the system's node partition, beside `META` | `T#kestrel#U#sys:<system>`, 2 items, none in the node partition |
| Redirect from the Function URL | Signed headers reached a second host | `AdapterError` with status 302, 0 requests to the second host |
| `skills_match: 50`, `years_experience: -40` | Ranked first with a score of 1.0 | Refused, naming the feature and not the value |
| Function URL drops the connection or truncates the body | `RemoteDisconnected`, `IncompleteRead` | `AdapterError` |
| Lambda payload is not JSON, or stalls after the headers | `JSONDecodeError` holding the body, `ReadTimeoutError` | `AdapterError` |
| DynamoDB hangs after a 4.5 s model call | Not tested | Returns in about 7.3 s, 2 attempts |
| `.lock` in the two pydantic zips (introduced by #48) | Shipped | Gone |

Undoing each fix in a throwaway clone fails a test, including the fixture's `LeadingKeys` condition, which no test covered before. The retrain reproduces `coefficients.json` and `golden.json`, with a holdout AUC of 0.8205.

The original criteria hold. Adapter shape tests pass. A test fails if a real Bedrock client appears anywhere. Pure-Python inference matches scikit-learn within `1e-9`. The largest zip is 2.5 MB. Simulated components are labelled. `verity crawl --local` gives 29 high findings, and `verity assess` alone 27.

One case is accepted: the model timeouts are per socket read, so a body that trickles in can pass the 10 s function timeout (12.3 s against a fake). The only server is our own mock, so no total deadline was added.

Open for M8: nothing here has run on AWS. The arm64 `pydantic_core` has never been loaded, because the zip tests use the host's copy. `LeadingKeys`, the permissions boundary, the SigV4 signing name and cold start at 128 MB are all unproven and are in the notes below.

## M8 live results (2026-11-06)

PR C ran the runbook against the real account. Full values are in [ADR 0027](adr/0027-m8-live-results.md). Opus reviewed it ([ADR 0028](adr/0028-m8-review.md)). The scheduled run passed on 2026-11-07, and M8 was closed that day on the owner's report that credits were unchanged ([ADR 0032](adr/0032-m8-scheduled-run.md), decision 5).

| Criterion | Result |
|---|---|
| All 5 functions classify as expected | Yes: `declared=3`, `none=4`, `probable=1`, one Candidate |
| An unsigned call to mock-openai is refused | Yes: 403 |
| Unused `bedrock:InvokeModel` finding appears | Yes: VC-060 fails on `support-assistant`, 29 high |
| CloudTrail shows no Bedrock use | 7 `List*` events by `resource-explorer-2`, no invocation |
| Second crawl idempotent | Yes: writes only the run |
| Destroying the estate then applying rebuilds it cleanly | Yes: same code hashes, table and budget untouched, crawl wrote only the run. 29 high still derived from the live table, in memory ([ADR 0028](adr/0028-m8-review.md)) |
| Credits unchanged | **Owner reported unchanged** on 2026-11-07 at about 11:05 UTC, against $120. This is an early report, under 24 hours after the latest one-off change, accepted by the owner as an exception ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 5). Reopen if a later read shows less |
| Scheduled run | **Passed** on 2026-11-07: a real cron run at 07:30 UTC under a temporary cron, `finished_at` set, 3 ChangeEvents. The cron was then reverted to `cron(0 3 * * ? *)`, which has not run yet ([ADR 0032](adr/0032-m8-scheduled-run.md)) |

## Notes for later milestones

Found while building and reviewing M1. Each is open until the named milestone closes it.

| Milestone | Note |
|---|---|
| M3 | **Closed 2026-11-07** on the owner's report that credits were unchanged against $120: an early report, accepted as an exception ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 5). Reopen if a later read shows less. The checks moto could not do are done ([ADR 0016](adr/0016-m3-live-results.md)) |
| M8 | `load_graph` reads every `U#` usage record in the table and discards it. Demo usage volume is small, so measure the scan on the real table. If usage grows large, load without a scan: list nodes through the type index and read each node's partition **Closed by [ADR 0028](adr/0028-m8-review.md).** |
| M8 | Read `DiscoveryRun.summary.largest_evidence_bytes` from the first live crawl. Evidence over the 16 KB cap is summarised, never refused ([ADR 0021](adr/0021-m6-discovery.md)); decide whether the cap should rise **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Build `crawler/handler.py` and the live path of `verity crawl`. The CLI refuses it until then **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Grant both Function URL actions, `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction`, to every caller of `mock-openai` ([ADR 0023](adr/0023-m7-demo-estate.md)) **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Write the `dynamodb:LeadingKeys` policy for each app role, limited to `T#kestrel#U#sys:<system>` using `ForAllValues:StringEquals`, with `dynamodb:PutItem` only. `shadow-summariser` and `talent-screening` get no table access **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Put a permissions boundary on the app roles that allows everything except `bedrock:Converse*`, `bedrock:Invoke*` and `sagemaker:InvokeEndpoint*`. `verity-never-use` is an inline policy on the user `rohpod`, so it does not cover a Lambda role, and nothing else stops `support-assistant` calling Bedrock ([ADR 0024](adr/0024-m7-review-fixes.md), correcting [ADR 0022](adr/0022-m6-review-fixes.md)). The grant stays in the role's policy so the VC-060 finding stands, and the UI must say the boundary makes it ineffective. Confirm the details and ask for approval first **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Prove the two limits, because moto does not enforce them: a real refused `PutItem` on a `META` item from a temporary probe, and the boundary with the IAM simulator. **Never attempt a Bedrock call,** even a refused one: it would count as use of the grant until M8 lands decision 3 of [ADR 0025](adr/0025-m8-deploy-and-crawl.md), and it could run for real if the boundary were wrong **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Measure cold start at 128 MB. `_dependencies` runs inside the handler, so importing boto3 and pydantic and creating two clients counts against the 10-second timeout, on top of the 9 to 9.5 seconds the model and telemetry budgets allow. If it does not fit, move that work to module load or raise the memory, which is free within the allowance only if the GB-seconds still fit **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Build the zips from a clean tree (`git status` empty): the build takes tracked files, so an uncommitted edit to one still ships **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Prove SigV4 against the real Function URL, including the signing name `lambda`, which no page read so far has confirmed. `tests/sdk` only proves the signature's shape **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Tag `mock-bedrock` and `mock-openai` `verity:component`. `mock-bedrock` is now in the fixture and in `platform_functions` **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Add manifest files under `content/manifests/` for `talent-screening` and `contract-insights`, then publish them **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Set each function's env values from the names in `tests/test_estate_parity.py`: `COEFFICIENTS_FILE=coefficients.json`, `HELP_ARTICLES_FILE=articles.json`, `INVOICE_TEMPLATE=template.txt`, `MODEL_ADAPTER=mock-bedrock`, and so on **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Upload the zips from `uv run python scripts/build_lambdas.py` directly (no S3). They are deterministic, so an unchanged build is not a ChangeEvent **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Grant the crawler the actions listed in architecture §D, and never `lambda:GetFunction` **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Tag the mocks and the crawler `verity:component`, or `mock-openai` becomes a shadow-AI candidate **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M8 | Publish the manifests to SSM under `/verity/manifests/` **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| After M8 | Decide whether to add Bedrock's 8 other `Invoke*` actions, such as `InvokeDataAutomation`, to `ai_signals.yaml` ([ADR 0025](adr/0025-m8-deploy-and-crawl.md)) |
| After M8 | Make `trail_shows_ai` check the event's name as `_proves` does, so a `List*` call from a function's role is not `confirmed_usage` ([ADR 0028](adr/0028-m8-review.md)) **Closed:** it now uses `_proves`, and the fix deployed on 2026-11-07 ([ADR 0032](adr/0032-m8-scheduled-run.md)) |
| After M8 | Stop `credential_process` running on every call for the operator's commands, and correct the CLI's "while it throttles" message ([ADR 0028](adr/0028-m8-review.md)) |
| M10 | Word the boundary note as what IAM's simulator shows, with no live call tried. Never say the grant "is ineffective" as a fact ([ADR 0028](adr/0028-m8-review.md)) |
| M8 | Confirm the real crawler's function name matches `platform_functions`, and that the demo role grants `bedrock:InvokeModel` **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| Before a re-seed | `verity seed` now reads every Evidence node to check decisions ([ADR 0020](adr/0020-m5-review-fixes.md)). Measure how long that takes once M6 evidence is in the table |
| Before a re-seed | Re-seeding removes nothing, so a mapping deleted from YAML stays open in the graph. Decide on pruning before the first live re-seed |
| M8 | The first `verity assess --target dynamodb` on the real content writes 1,368 records (65 `APPLIES_TO` edges, 433 ControlAssessments, 870 assessment edges): about 5,900 write units, roughly 6.6 minutes at 15 table units a second, and a second run writes 0. Measured on the in-memory copy that `estimate_apply` uses. It is not yet run on the real table. Decisions that change only add or close a few records **Closed by [ADR 0027](adr/0027-m8-live-results.md).** |
| M9 | Replace the `acct_` account digests with ordinals on export. A digest is not anonymous ([ADR 0022](adr/0022-m6-review-fixes.md)). Ordinals alone are not enough: the hashes must go too ([ADR 0029](adr/0029-m9-snapshot-export.md)) |
| M9 | A decision's commit SHA is looked up at export, not at seed, because a SHA inside hashed content would make a new Evidence node on every commit ([ADR 0019](adr/0019-m5-rules-and-assessment.md), D10). Build the lookup from the decision's file path and `file_sha256` |
| M9 | PR C: a live export must use now, not the start of the day, as `verity assess` does. The commit SHA field needs its own exemption from the digit rule. Run the scan on the first live file first ([ADR 0030](adr/0030-m9-redaction-review.md)) |
| Standing | Edge writes do not re-check the nodes they connect, which is safe with one writer at a time ([ADR 0014](adr/0014-m2-measurements-and-evidence-cap.md)). Do not run a seed and a crawl together |
| M11 | Risk treatment decisions, named in [ADR 0008](adr/0008-governance-as-code.md), are deferred because nothing reads them ([ADR 0019](adr/0019-m5-rules-and-assessment.md)). Build them or drop them from ADR 0008 |
| M11 | Three obligation dates are read by no rule, because nothing in the content or the estate falls under them: `euaia-omnibus-in-force`, `euaia-art5-new` and `euaia-high-risk-annex-i`. Revisit if a system or requirement needs one |
| M11 | Art. 10(5) moved to the new Art. 4a, which allows special-category data for bias testing under strict conditions. The bias-test control does not cover it, because Kestrel records no special-category processing ([ADR 0019](adr/0019-m5-rules-and-assessment.md)). Revisit if that changes |
| M11 | D15 overstates its reason: Policy, Dataset, Candidate and DiscoveryRun appear in none of the 5 traversals. They stay, because other views need them |

**AWS mutations happen only in M3, M8 and any M11 teardown or refresh.** Each needs its own approval, with what it creates, the verified price and how to delete it.


## M11 close register (draft)

_Drafted by Sonnet from [the M10 and M11 plan](m10-m11-plan.md), step 1. It covers the 6 §L items, every ❓ in Stage 2, the ADRs and the architecture, and every row in "Notes for later milestones". **Nothing here is decided.** A proposed state only repeats what a merged document already records; where closing a row would take a decision, the row says "open" and names who decides. Every row is a draft until Opus confirms it. M11's validation criterion is that every row is closed or explicitly deferred, with a reason._

| ID | Item | Source | Proposed state | Basis or reason | Status |
|---|---|---|---|---|---|
| L1 | Org-level obligations: `APPLIES_TO` targets `Organisation`, and `Control.scope_level` gives inheritance | [architecture §L](architecture.md#l-schema-validation-walkthrough) | closed | Reflected in §E, and the five traversals are re-checked by executable tests (`tests/graph/test_traversals.py`, M1 ✅) | draft: Opus to confirm |
| L2 | Vendor evidence: `Evidence ABOUT <any node>` and `ControlAssessment SCOPED_TO Provider` | [architecture §L](architecture.md#l-schema-validation-walkthrough) | closed | Reflected in §E, and the five traversals are re-checked by executable tests (`tests/graph/test_traversals.py`, M1 ✅) | draft: Opus to confirm |
| L3 | In-house models: `Model.origin`, and `PROVIDED_BY` for third-party models only | [architecture §L](architecture.md#l-schema-validation-walkthrough) | closed | Reflected in §E, and the five traversals are re-checked by executable tests (`tests/graph/test_traversals.py`, M1 ✅) | draft: Opus to confirm |
| L4 | Requirement granularity: `PART_OF` can point to a parent `Requirement` | [architecture §L](architecture.md#l-schema-validation-walkthrough) | closed | Reflected in §E, and the five traversals are re-checked by executable tests (`tests/graph/test_traversals.py`, M1 ✅) | draft: Opus to confirm |
| L5 | Accountability for L4: the `Person ASSESSED ControlAssessment` edge | [architecture §L](architecture.md#l-schema-validation-walkthrough) | closed | Reflected in §E, and the five traversals are re-checked by executable tests (`tests/graph/test_traversals.py`, M1 ✅) | draft: Opus to confirm |
| L6 | Candidate lifecycle: `Candidate DERIVED_FROM AWSResource` and `PROMOTED_TO AISystem` | [architecture §L](architecture.md#l-schema-validation-walkthrough) | closed | Reflected in §E, and the five traversals are re-checked by executable tests (`tests/graph/test_traversals.py`, M1 ✅) | draft: Opus to confirm |
| E1 | Lambda Function URLs: no separate price (Stage 2 ❓) | [Stage 2](stage-2-feasibility.md) | closed | [ADR 0025](adr/0025-m8-deploy-and-crawl.md) pricing table cites AWS's own statement that they are included in the cost of invoking Lambda; M8's pricing criterion is recorded as passed in [open milestones](open-milestones.md) | draft: Opus to confirm |
| E2 | SSM Parameter Store (standard) is free (Stage 2 ❓) | [Stage 2](stage-2-feasibility.md) | closed | ADR 0025 pricing table: no additional charge; the Free plan accepted SSM at L4 (ADR 0027) | draft: Opus to confirm |
| E3 | Bedrock / SageMaker real inference, "Decision D1" (Stage 2 ❓) | [Stage 2](stage-2-feasibility.md) | closed | Decided mock-only: [ADR 0007](adr/0007-mock-only-ai-providers.md) and the honesty rules in CLAUDE.md | draft: Opus to confirm |
| E4 | CycloneDX v1.7 may exist (Stage 2 ❓) | [Stage 2](stage-2-feasibility.md) | open: Opus decides | Nothing built uses CycloneDX. It appears only as a Stage 1 feature idea ("AI-BOM export"). Defer or drop is a scope decision, so it is not made here | draft: Opus to confirm |
| E5 | ISO 27001:2022 Amendment 1:2024 wording, "confirm when we seed controls" (Stage 2 ❓) | [Stage 2](stage-2-feasibility.md) | open: Opus confirms | `content/frameworks/iso27001.yaml` and `content/mappings/iso27001.yaml` record that Amendment 1 touches clauses 4.1 and 4.2, per public sources, and that nothing in the library covers the climate question. Whether that satisfies the note is a content judgement | draft: Opus to confirm |
| E6 | STRM definitions checked only through the SCF summary (ADR 0004 ❓) | [ADR 0004](adr/0004-hub-and-spoke-strm-crosswalk.md) | closed | Stage 4 "M4 re-verification": the 5 types and 3 rationales match `enums.py`, NIST IR 8477 final read in full | draft: Opus to confirm |
| E7 | `python3.12` on arm64 (architecture §B ❓) | [Stage 4](stage-4-milestones.md) | closed | Stage 4 "Findings from read-only checks" records it as closed | draft: Opus to confirm |
| E8 | `aws login` flow (architecture §J ❓) | Stage 4 | closed | Stage 4 "Findings from read-only checks" records it as closed | draft: Opus to confirm |
| E9 | Whether Free plan accounts may use EventBridge Scheduler, SSM and IAM ("Still unverified") | [ADR 0025](adr/0025-m8-deploy-and-crawl.md) consequences | closed | [ADR 0027](adr/0027-m8-live-results.md), L4: the Free plan accepted IAM, Scheduler and SSM | draft: Opus to confirm |
| N1 | M3: owner's credit read (reported unchanged early, on 2026-11-07) | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed on the owner's report | L15 passed on 2026-11-07, and the owner reported credits unchanged the same day, before the 24-hour mark ([ADR 0032](adr/0032-m8-scheduled-run.md) decision 5). Reopen if a later read shows less. Not an M11 decision | draft: Opus to confirm |
| N2 | M8: `load_graph` scans every `U#` record | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0028](adr/0028-m8-review.md) | draft: Opus to confirm |
| N3 | M8: Read `largest_evidence_bytes` from the first live crawl; decide the 16 KB cap | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N4 | M8: Build `crawler/handler.py` and the live path of `verity crawl` | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N5 | M8: Both Function URL actions for every caller of `mock-openai` | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N6 | M8: `dynamodb:LeadingKeys` policy per app role | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N7 | M8: Permissions boundary on the app roles | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N8 | M8: Prove the two limits (refused `PutItem`, IAM simulator) | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N9 | M8: Cold start at 128 MB | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N10 | M8: Build zips from a clean tree | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N11 | M8: SigV4 against the real Function URL | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N12 | M8: Tag `mock-bedrock` and `mock-openai` `verity:component` | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N13 | M8: Manifest files for `talent-screening` and `contract-insights` | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N14 | M8: Set each function's env values from the parity test | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N15 | M8: Upload deterministic zips directly (no S3) | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N16 | M8: Grant the crawler the §D actions, never `lambda:GetFunction` | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N17 | M8: Tag the mocks and the crawler, or `mock-openai` becomes a candidate | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N18 | M8: Publish the manifests to SSM | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N19 | M8: Confirm the crawler's name matches `platform_functions`, and the demo role's `bedrock:InvokeModel` | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N20 | M8: First `assess --target dynamodb` write estimate | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Marked closed in the notes by [ADR 0027](adr/0027-m8-live-results.md) | draft: Opus to confirm |
| N21 | After M8: Bedrock's 8 other `Invoke*` actions in `ai_signals.yaml` | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones), [ADR 0025](adr/0025-m8-deploy-and-crawl.md) | open: Opus decides (step 3) | Not decided here | draft: Opus to confirm |
| N22 | After M8: `trail_shows_ai` checks the event name as `_proves` does | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones), [ADR 0028](adr/0028-m8-review.md) | closed; deployed on 2026-11-07 | Marked closed in the notes. The fix went out with the L15 apply, and the 07:30 UTC run used it ([ADR 0032](adr/0032-m8-scheduled-run.md)) | draft: Opus to confirm |
| N23 | After M8: `credential_process` on every operator call, and the CLI's "while it throttles" message | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones), ADR 0028 | open: Sonnet, step 2 | Not started in this PR. See the files report in the PR description | draft: Opus to confirm |
| N24 | M10: word the boundary note as what IAM's simulator shows; never say the grant "is ineffective" | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | `BOUNDARY_NOTE` in `web/src/lib/wording.ts` ([ADR 0031](adr/0031-m10-dashboard.md) "UI duties"), tested in `web/src/test/duties.test.tsx`, shown in the System profile and, since PR 65, the Controls detail | draft: Opus to confirm |
| N25 | Before a re-seed: time the Evidence read that `verity seed` does | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones), [ADR 0020](adr/0020-m5-review-fixes.md) | partly measured | ADR 0027 decision 3 measured a first seed (about 11 minutes). A re-seed has not been measured | draft: Opus to confirm |
| N26 | Before a re-seed: re-seeding removes nothing, so a deleted mapping stays open | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | open: Opus decides (step 3) | Not decided here | draft: Opus to confirm |
| N27 | M9: replace `acct_` digests with ordinals on export | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones), [ADR 0029](adr/0029-m9-snapshot-export.md) | closed | Proved on live data on 2026-11-07: 0 scan hits and the Opus review ([ADR 0033](adr/0033-m9-live-snapshot.md)) | draft: Opus to confirm |
| N28 | M9: look up a decision's commit SHA at export | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | closed | Proved on live data on 2026-11-07: 0 scan hits and the Opus review ([ADR 0033](adr/0033-m9-live-snapshot.md)) | draft: Opus to confirm |
| N29 | M9 PR C: now as `as_of`, an exemption for the SHA, and scan the first live file first | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones), ADR 0030 | closed | Proved on live data on 2026-11-07: 0 scan hits and the Opus review ([ADR 0033](adr/0033-m9-live-snapshot.md)) | draft: Opus to confirm |
| N30 | Standing: edge writes do not re-check their nodes, so one writer at a time; never run a seed and a crawl together | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones), [ADR 0014](adr/0014-m2-measurements-and-evidence-cap.md) | standing | Not closeable. Carried into [the final snapshot runbook](runbooks/m11-final-snapshot.md), including the daily schedule once it is enabled | draft: Opus to confirm |
| N31 | M11: risk treatment decisions (ADR 0008): build them or drop them | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones), [ADR 0008](adr/0008-governance-as-code.md) | open: Opus decides (step 3) | Not decided here | draft: Opus to confirm |
| N32 | M11: three obligation dates read by no rule (`euaia-omnibus-in-force`, `euaia-art5-new`, `euaia-high-risk-annex-i`) | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | open: Opus decides (step 3) | Regulatory. Not decided here | draft: Opus to confirm |
| N33 | M11: Art. 10(5) moved to the new Art. 4a | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones), [ADR 0019](adr/0019-m5-rules-and-assessment.md) | open: Opus decides (step 3) | Regulatory. Not decided here | draft: Opus to confirm |
| N34 | M11: D15 overstates its reason | [Stage 4 notes](stage-4-milestones.md#notes-for-later-milestones) | open: Opus decides (step 3) | Wording of a decision. Not changed here | draft: Opus to confirm |
| R1 | `npm audit`: 7 moderate advisories in dev tooling (typescript-eslint's `minimatch`) | [ADR 0031](adr/0031-m10-dashboard.md) consequences | open: M11 security review (step 5) | Nothing in it ships. Raised during M10, so not in the original lists | draft: Opus to confirm |
