# Stage 4 — Milestone plan

_2026-11-05 · Approved. Status key: ⬜ not started · 🔄 in progress · ✅ validated._
Inputs: [architecture](architecture.md) · [ADRs](adr/). Decisions by the owner: mock-openai uses an `AWS_IAM` Function URL ([ADR 0009](adr/0009-mock-openai-iam-auth.md)); milestones run AWS first, UI last.

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
| Function URL pricing unconfirmed | Verify on the Function URL docs before M8 |

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

## Milestones

| | Milestone | Lead | AWS mutation | Status |
|---|---|---|---|---|
| **Core engine (local)** | | | | |
| M0 | Foundations: uv workspace, ruff, pytest, CI without AWS credentials, Dependabot, mutating-command hook | Sonnet | no | ✅ |
| M1 | Graph core: models, IDs, `GraphRepository`, `InMemoryRepository`, NetworkX loader, traversals | Opus, then Sonnet | no | ✅ |
| M2 | `DynamoDBRepository` (moto), shared contract suite | Sonnet | no | ✅ |
| **AWS baseline** | | | | |
| M3 | Account baseline: non-root admin with MFA, region eu-north-1, `infra/` root, $0.01 budget, `verity-graph` | Opus (IAM), Sonnet | **yes, approval first** | 🔄 |
| **Governance logic (local)** | | | | |
| M4 | Content: hub controls, ~35 requirements, STRM mappings, Kestrel org, synthetic systems, `verity seed` | Sonnet builds the loader, linter, CLI and org data; Opus writes the regulatory content | no | ✅ |
| M5 | Rules and assessment: applicability, status, assurance, satisfaction, `verity assess`, `verity attest` | Opus, then Sonnet | no | ✅ |
| M6 | Discovery pipeline (8 stages), `ai_signals.yaml`, `verity crawl --local` | Sonnet | no | ✅ |
| M7 | Demo estate code: mocks, `verity_ai` with SigV4 hook, 5 apps, local talent model | Sonnet | no | 🔄 |
| **Live** | | | | |
| M8 | Deploy and first live crawl: Lambda modules, schedule, SSM manifests, guardrails | Opus (IAM), Sonnet | **yes, approval per apply** | ⬜ |
| **Public demo** | | | | |
| M9 | Snapshot export, redaction, schema, generated TS types | Sonnet; Opus reviews redaction | no | ⬜ |
| M10 | Dashboard in three slices, GitHub Pages | Sonnet | no | ⬜ |
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
- **M8:** Function URL pricing confirmed first; all 5 functions classify as expected; an unsigned call to mock-openai is refused; unused `bedrock:InvokeModel` finding appears and CloudTrail shows no Bedrock use; second crawl idempotent; `tofu destroy` then apply rebuilds cleanly; credits unchanged.
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

## Notes for later milestones

Found while building and reviewing M1. Each is open until the named milestone closes it.

| Milestone | Note |
|---|---|
| M3 | Last open criterion: the owner re-reads credits in the Billing console at least 24 hours after the last live write (2026-11-05). M3 stays 🔄 until they match. The checks moto could not do are done ([ADR 0016](adr/0016-m3-live-results.md)) |
| M8 | `load_graph` reads every `U#` usage record in the table and discards it. Demo usage volume is small, so measure the scan on the real table. If usage grows large, load without a scan: list nodes through the type index and read each node's partition |
| M8 | Read `DiscoveryRun.summary.largest_evidence_bytes` from the first live crawl. Evidence over the 16 KB cap is summarised, never refused ([ADR 0021](adr/0021-m6-discovery.md)); decide whether the cap should rise |
| M8 | Build `crawler/handler.py` and the live path of `verity crawl`. The CLI refuses it until then |
| M8 | Grant both Function URL actions, `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction`, to every caller of `mock-openai` ([ADR 0023](adr/0023-m7-demo-estate.md)) |
| M8 | Write the `dynamodb:LeadingKeys` policy for each app role, limited to `T#kestrel#N#sys:<system>`, with `dynamodb:PutItem` only. `shadow-summariser` and `talent-screening` get no table access |
| M8 | Prove SigV4 against the real Function URL, including the signing name `lambda`, which no page read so far has confirmed. `tests/sdk` only proves the signature's shape |
| M8 | Tag `mock-bedrock` and `mock-openai` `verity:component`. `mock-bedrock` is now in the fixture and in `platform_functions` |
| M8 | Add manifest files under `content/manifests/` for `talent-screening` and `contract-insights`, then publish them |
| M8 | Set each function's env values from the names in `tests/test_estate_parity.py`: `COEFFICIENTS_FILE=coefficients.json`, `HELP_ARTICLES_FILE=articles.json`, `INVOICE_TEMPLATE=template.txt`, `MODEL_ADAPTER=mock-bedrock`, and so on |
| M8 | Upload the zips from `uv run python scripts/build_lambdas.py` directly (no S3). They are deterministic, so an unchanged build is not a ChangeEvent |
| M8 | Grant the crawler the actions listed in architecture §D, and never `lambda:GetFunction` |
| M8 | Tag the mocks and the crawler `verity:component`, or `mock-openai` becomes a shadow-AI candidate |
| M8 | Publish the manifests to SSM under `/verity/manifests/` |
| M8 | Check the AI action list in `ai_signals.yaml` against the IAM reference, which could not be read while building M6 ([ADR 0022](adr/0022-m6-review-fixes.md)) |
| M8 | Confirm the real crawler's function name matches `platform_functions`, and that the demo role grants `bedrock:InvokeModel` |
| M8 | `verity seed` now reads every Evidence node to check decisions ([ADR 0020](adr/0020-m5-review-fixes.md)). Measure how long that takes once M6 evidence is in the table |
| M8 | Re-seeding removes nothing, so a mapping deleted from YAML stays open in the graph. Decide on pruning before the first live re-seed |
| M8 | The first `verity assess --target dynamodb` on the real content writes 1,368 records (65 `APPLIES_TO` edges, 433 ControlAssessments, 870 assessment edges): about 5,900 write units, roughly 6.6 minutes at 15 table units a second, and a second run writes 0. Measured on the in-memory copy that `estimate_apply` uses. It is not yet run on the real table. Decisions that change only add or close a few records |
| M9 | Replace the `acct_` account digests with ordinals on export. A digest is not anonymous ([ADR 0022](adr/0022-m6-review-fixes.md)) |
| M9 | A decision's commit SHA is looked up at export, not at seed, because a SHA inside hashed content would make a new Evidence node on every commit ([ADR 0019](adr/0019-m5-rules-and-assessment.md), D10). Build the lookup from the decision's file path and `file_sha256` |
| M8 | Edge writes do not re-check the nodes they connect, which is safe with one writer at a time ([ADR 0014](adr/0014-m2-measurements-and-evidence-cap.md)). Do not run a seed and a crawl together |
| M11 | Risk treatment decisions, named in [ADR 0008](adr/0008-governance-as-code.md), are deferred because nothing reads them ([ADR 0019](adr/0019-m5-rules-and-assessment.md)). Build them or drop them from ADR 0008 |
| M11 | Three obligation dates are read by no rule, because nothing in the content or the estate falls under them: `euaia-omnibus-in-force`, `euaia-art5-new` and `euaia-high-risk-annex-i`. Revisit if a system or requirement needs one |
| M11 | Art. 10(5) moved to the new Art. 4a, which allows special-category data for bias testing under strict conditions. The bias-test control does not cover it, because Kestrel records no special-category processing ([ADR 0019](adr/0019-m5-rules-and-assessment.md)). Revisit if that changes |
| M11 | D15 overstates its reason: Policy, Dataset, Candidate and DiscoveryRun appear in none of the 5 traversals. They stay, because other views need them |

**AWS mutations happen only in M3, M8 and any M11 teardown or refresh.** Each needs its own approval, with what it creates, the verified price and how to delete it.
