# Stage 4 — Milestone plan

_2026-11-05 · Approved. Status key: ⬜ not started · 🔄 in progress · ✅ validated._
Inputs: [architecture](architecture.md) · [ADRs](adr/). Decisions by the owner: mock-openai uses an `AWS_IAM` Function URL ([ADR 0009](adr/0009-mock-openai-iam-auth.md)); milestones run AWS first, UI last.

## Findings from read-only checks (2026-11-05)

| Finding | Effect |
|---|---|
| Plan expires **4 May 2027**; $100 credits left; no Lambda functions or DynamoDB tables in eu-west-1 | Take the last live snapshot by **1 Apr 2027** |
| Lambda account concurrency is **10**; AWS requires 100 to stay unreserved | Reserved concurrency can't be set; dropped ([ADR 0009](adr/0009-mock-openai-iam-auth.md)) |
| `ListFunctions` returns env var values | IAM can't enforce "names only"; the crawler discards values on receipt (D1) |
| CLI session is **root**; default region is **ap-south-1** | **Updated:** the CLI now uses IAM user `rohpod` in **eu-north-1** ([ADR 0011](adr/0011-region-eu-north-1.md)). The user has **no permissions yet**, so M3 must grant them |
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
| D14 | GSI projects keys only; `H#` written only on real change; writes retry with backoff; inline evidence cap set from M2 measurements |
| D15 | All 18 node types are kept, because the §L traversals need them |
| D16 | Schema refinements found while planning M1. See [ADR 0012](adr/0012-graph-schema-refinements.md) |
| D17 | How `DynamoDBRepository` writes and reads. See [ADR 0013](adr/0013-dynamodb-write-model.md) |

## Milestones

| | Milestone | Lead | AWS mutation | Status |
|---|---|---|---|---|
| **Core engine (local)** | | | | |
| M0 | Foundations: uv workspace, ruff, pytest, CI without AWS credentials, Dependabot, mutating-command hook | Sonnet | no | ✅ |
| M1 | Graph core: models, IDs, `GraphRepository`, `InMemoryRepository`, NetworkX loader, traversals | Opus, then Sonnet | no | ✅ |
| M2 | `DynamoDBRepository` (moto), shared contract suite | Sonnet | no | 🔄 |
| **AWS baseline** | | | | |
| M3 | Account baseline: non-root admin with MFA, region eu-north-1, `infra/` root, $0.01 budget, `verity-graph` | Opus (IAM), Sonnet | **yes, approval first** | ⬜ |
| **Governance logic (local)** | | | | |
| M4 | Content: hub controls, ~35 requirements, STRM mappings, Kestrel org, synthetic systems, `verity seed` | Opus | no | ⬜ |
| M5 | Rules and assessment: applicability, status, assurance, satisfaction, `verity assess`, `verity attest` | Opus, then Sonnet | no | ⬜ |
| M6 | Discovery pipeline (8 stages), `ai_signals.yaml`, `verity crawl --local` | Sonnet | no | ⬜ |
| M7 | Demo estate code: mocks, `verity_ai` with SigV4 hook, 5 apps, local talent model | Sonnet | no | ⬜ |
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
- **M8:** Function URL pricing confirmed first; all 5 functions classify as expected; an unsigned call to mock-openai is refused; unused `bedrock:Converse` finding appears and CloudTrail shows no Bedrock use; second crawl idempotent; `tofu destroy` then apply rebuilds cleanly; credits unchanged.
- **M9:** scans of a snapshot built from live data find no account ID, Function URL host, env value or email; schema validates; every record has provenance and the file has its `as_of`.
- **M10:** typecheck and build pass; `snapshot.json` is the only data source; every view shows provenance and timestamp; works at phone width; Pages URL works.
- **M11:** every §L and ❓ item is closed or explicitly deferred; the README real-vs-simulated table matches what was built.

## Notes for later milestones

Found while building and reviewing M1. Each is open until the named milestone closes it.

| Milestone | Note |
|---|---|
| M3 | The real round trip must check what moto cannot: the table class (moto ignores it), GSI delay, and transaction capacity |
| M3 | Check how a throttled `TransactWriteItems` is reported on the real table: as `ProvisionedThroughputExceededException` (boto3 retries it) or as a cancellation with reason `ProvisionedThroughputExceeded` (the repository retries it). AWS's pages do not say which |
| M4 | A first seed of about 300 nodes and 1,000 edges needs about 5,200 write units, roughly 6 minutes at the table's 15 per second ([ADR 0013](adr/0013-dynamodb-write-model.md)). `verity seed` should expect throttling waits and report progress. Re-seeding writes almost nothing |
| M6 | `load_graph` reads every `U#` usage record in the table and discards it. If usage grows large, load without a scan: list nodes through the type index and read each node's partition |
| M2, M6 | Daily `OBSERVED` edges could reach thousands of items by April 2027 and strain §H's size assumption. Measure it |
| M5 | Art. 9 shows `unmapped` when only its sub-clause is mapped. Decide whether a parent inherits from its children |
| M5 | `unmapped` covers both "never mapped" and "reviewed, `no_relationship`". Decide whether *Not addressed* (D2) treats them alike |
| M5 | `provider_unknown` must be a finding, never *Not applicable* |
| M6 | Stamp `ChangeEvent.detected_at` at run start, so evidence collected in the same run survives. Leave `valid_from` unset on re-crawls, or every run writes history |
| M6 | §D says "system → provider", but §E only has the path through Model. Decide how to record a provider with no known model |
| M11 | D15 overstates its reason: Policy, Dataset, Candidate and DiscoveryRun appear in none of the 5 traversals. They stay, because other views need them |

**AWS mutations happen only in M3, M8 and any M11 teardown or refresh.** Each needs its own approval, with what it creates, the verified price and how to delete it.
