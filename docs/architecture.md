# Verity — Architecture

_Stage 3 deliverable · 2026-11-05 · Status: accepted, amended in Stage 4 (see [milestone plan](stage-4-milestones.md), [ADR 0009](adr/0009-mock-openai-iam-auth.md), [ADR 0010](adr/0010-assessment-and-crosswalk-semantics.md), [ADR 0012](adr/0012-graph-schema-refinements.md), [ADR 0013](adr/0013-dynamodb-write-model.md))._
Inputs: [Stage 1 discovery](stage-1-discovery.md) · [Stage 2 feasibility](stage-2-feasibility.md) · decisions in [`adr/`](adr/).

**Locked constraints:** AWS Free plan · single region `eu-north-1` · Terraform/OpenTofu · Python 3.12 backend · React + TS frontend · DynamoDB + NetworkX graph · no S3 · Bedrock/OpenAI mock-only · public demo = static snapshot on GitHub Pages · target customer = mid-size EU SaaS company acting as both AI provider and deployer.

---

## A. High-level architecture

```
                    ┌──────────────── AWS account (eu-north-1, Free plan) ─────────────────┐
  Demo AI estate    │  [support-assistant λ] ──invoke──▶ [mock-bedrock λ]  (Converse shape) │
  (the fictional    │  [talent-screening λ]  (real model, pure-Python inference)           │
   customer's       │  [contract-insights λ] ──HTTPS──▶ [mock-openai λ URL, AWS_IAM] (/v1/chat/…)    │
   workloads)       │  [shadow-summariser λ] (untagged, no manifest → must be detected)    │
                    │  [invoice-renderer λ]  (not AI → must NOT be flagged)                │
                    │  SSM /verity/manifests/*  (ai-manifest.yaml, published by Terraform) │
                    │                                                                      │
  Verity platform   │  EventBridge Scheduler (daily) ──▶ [verity-crawler λ]                │
                    │      read-only discovery role + write to its own table only │        │
                    │                                                             ▼        │
                    │                           DynamoDB `verity-graph` (provisioned 25/25)│
                    │  Guardrails: Budgets alert · 3-day log retention                      │
                    └───────────────────────────────────────────┬──────────────────────────┘
                                                                │ boto3 (admin IAM user, MFA)
  Laptop:  `verity` CLI ── seed (YAML) · assess · export ──▶ web/public/data/snapshot.json
                                                                │ (account ID redacted)
  GitHub:  repo ──Actions──▶ GitHub Pages: React dashboard reading snapshot.json (public demo)
```

**Core principle:** one shared Python library, `verity_core`, holds the domain model, graph repository, discovery pipeline, rules and assessment engine. The crawler Lambda, the CLI and the tests are thin shells around it, so almost everything runs and is tested **locally without AWS**.

## B. Repository layout

```
verity/
  core/verity_core/   model/      pydantic node & edge types, enums, ID helpers
                      graph/      GraphRepository protocol, InMemory + DynamoDB impls, NetworkX loader
                      discovery/  collectors · enrichers · signals/scoring · correlation · diff
                      rules/      applicability engine (system attributes × role × date → requirements)
                      assess/     control status, assurance level, requirement satisfaction, rollups
                      export/     snapshot builder + redaction
                      cli.py      `verity` command
  crawler/            handler.py — thin Lambda entrypoint
  sdk/verity_ai/      provider adapters (BedrockCompatible, OpenAICompatible) + usage telemetry
  apps/               support_assistant · talent_screening · contract_insights · shadow_summariser · invoice_renderer
  mocks/              mock_bedrock · mock_openai
  content/            frameworks/ · controls.yaml · mappings/ · rules/ · org/ · manifests/ · decisions/
  infra/              Terraform root + modules (lambda_app, crawler, table, guardrails)
  web/                Vite + React + TS dashboard
  tests/  docs/  .github/workflows/
```

**Tooling:** `uv` (Python 3.12; the macOS system Python 3.9 is EOL), pydantic v2, NetworkX, pytest + `moto`, ruff. Lambdas run on arm64; Linux wheels are vendored with `uv pip install --python-platform aarch64-manylinux2014`. `python3.12` is supported on arm64, with deprecation forecast for 31 Oct 2028 ✅ (verified 2026-11-05). IaC uses OpenTofu (`tofu`).

## C. Demo AI estate

| | **Support Assistant** | **Talent Screening** | **Contract Insights** |
|---|---|---|---|
| Kind | Generative AI chatbot | Classical ML | External AI API integration |
| Purpose | Answer customer support questions | Rank job applicants for recruiters | Summarise customer contracts for sales and legal |
| Model / provider | "Bedrock foundation model". **Simulated** by mock-bedrock (Converse-shaped) | Logistic regression trained locally on **synthetic** data; coefficients shipped as JSON. **Real** | "OpenAI GPT-class model". **Simulated** by mock-openai |
| Data | Help-centre articles (Public); customer messages (Confidential, personal data) | Applicant profiles (Restricted, personal data) | Customer contracts (Confidential) |
| EU AI Act screening | Limited risk: Art. 50(1) transparency. Role: provider + deployer | **Annex III §4(a) employment → high-risk candidate.** Obligations apply from **2 Dec 2027** | Minimal risk. Third-party / downstream-provider considerations |
| Governance story | Transparency, human handoff, logging | Bias, data governance, human oversight, technical documentation | Vendor risk, cross-border data transfer, confidentiality |
| Seeded finding | Role grants `bedrock:Converse` but **no usage is observed**. This is a least-privilege finding; the permission is never exercised, in keeping with the mock-only rule | No bias-test evidence → gap | No DPA evidence for the provider → gap |

**Crawler test fixtures:**
- `shadow-summariser` has no tags and no manifest but has an `OPENAI_BASE_URL` env var. It must be classified *probable* and surface as a shadow-AI candidate.
- `invoice-renderer` is an ordinary function and must be classified *none*.

**Synthetic estate:** about 25 additional AI systems for the fictional **Kestrel Cloud Ltd**, with `source=synthetic` and no AWS resources, so posture charts have realistic volume. Every record in the UI carries a provenance badge: **Live-discovered · Declared · Synthetic**.

## D. Discovery crawler

The pipeline is a sequence of pure functions over plain data, so it can be unit-tested with `moto` and recorded fixtures.

| # | Stage | What it does |
|---|---|---|
| 1 | Enumerate | `tag:GetResources`, `lambda:ListFunctions`, `iam:ListRoles`, `dynamodb:ListTables`, `ssm:GetParametersByPath(/verity/manifests)`. Resource Explorer `Search` is optional and uses the local index only, never Config-backed views. |
| 2 | Enrich | Function configuration (runtime, role, architecture). **Env var *names* only.** `ListFunctions` returns values too, so the collector discards them on receipt: never stored, never logged, and covered by a canary test. Tags. Inline and attached role policies. |
| 3 | Signal & score | Rules in `content/rules/ai_signals.yaml` combine signals into `ai_likelihood ∈ {declared, confirmed_usage, probable, possible, none}`. Every result stores the signals that fired, so the UI can explain *why*. |
| 4 | Correlate | The `ai:system-id` tag or a manifest links a resource to an `AISystem`. Unlinked resources scored *probable* or *possible* become `Candidate`s (the shadow-AI inbox). |
| 5 | Relate | `ASSUMES` (function → role) and `CALLS` (function → table/function, derived from IAM resource ARNs and env var names). Also system → provider. |
| 6 | Usage | `verity_ai` adapters write `U#` usage records (system, provider, model, timestamp, token estimate). This is evidence of **actual AI usage**, as opposed to infrastructure merely existing. CloudTrail `LookupEvents` is also queried for `bedrock:*`; the honest expected result is *none observed*. |
| 7 | Diff | Config hashes are compared with the previous run to produce `ChangeEvent`s. Evidence collected from a changed resource becomes **stale**. |
| 8 | Persist | Idempotent upserts with deterministic IDs, plus a `DiscoveryRun` node for provenance. |

**Signal ladder (summary):**

| Signal | Strength |
|---|---|
| Manifest or `ai:system-id` tag | declared |
| Usage records or CloudTrail AI events | confirmed_usage |
| IAM grants AI actions; AI-named env vars | probable |
| Name or description heuristics | possible |

**IAM:** a custom least-privilege policy, rather than the broader AWS-managed `SecurityAudit`. It deliberately excludes `lambda:GetFunction` (which would allow code download), and its only write access is to `verity-graph`.

## E. Knowledge graph schema

### Node types (MVP)

| Group | Types |
|---|---|
| Organisation | `Organisation`, `Department`, `Person` |
| AI estate | `AISystem`, `Candidate`, `AWSResource`, `Model`, `Provider`, `Dataset` |
| Governance | `Risk`, `Control`, `ControlAssessment`, `Requirement`, `Framework`, `Evidence`, `Policy` |
| Provenance | `DiscoveryRun`, `ChangeEvent` |
| Later | `RemediationTask`, `Exception` |

**Notes on modelling choices:**
- `DataClassification` is an enum property on `Dataset` (Public · Internal · Confidential · Restricted, plus a `personal_data` flag), not a node. We can promote it to a node later if controls start attaching to classifications.
- `Model.origin ∈ {in_house, third_party}`. Only third-party models get `PROVIDED_BY`.
- `Provider.simulated: bool` makes mocks explicit in the data itself.
- **The tenant is the organisation:** each tenant has exactly one `Organisation`, enforced on write, so a system finds its organisation without an edge ([ADR 0012](adr/0012-graph-schema-refinements.md)).

### Identifiers

IDs are deterministic and typed, which makes re-crawls idempotent:
- `sys:talent-screening`
- `res:lambda:eu-north-1:talent-screening`
- `fw:euaia`
- `req:euaia:art50-1`
- `req:iso42001:A.6.2.4`
- `req:nistrmf:MAP-1.1`
- `ctl:VC-014`
- `ev:<sha256-prefix>`, 32 hex characters, where the hash covers subject + collector + `collected_at` + the content's `sha256` ([ADR 0010](adr/0010-assessment-and-crosswalk-semantics.md), [ADR 0012](adr/0012-graph-schema-refinements.md))
- `ca:VC-014:sys:talent-screening`, one node per control × scope
- `res:iam-role:global:<name>` for resources without a region

| Node type | Prefix | | Node type | Prefix |
|---|---|---|---|---|
| Organisation | `org:` | | Risk | `risk:` |
| Department | `dept:` | | Control | `ctl:` |
| Person | `person:` | | ControlAssessment | `ca:` |
| AISystem | `sys:` | | Requirement | `req:` |
| Candidate | `cand:` | | Framework | `fw:` |
| AWSResource | `res:` | | Evidence | `ev:` |
| Model | `model:` | | Policy | `pol:` |
| Provider | `prov:` | | DiscoveryRun | `run:` |
| Dataset | `ds:` | | ChangeEvent | `chg:` |

IDs use only `[A-Za-z0-9._:-]`, so they can never corrupt a `#`-delimited key.

Every node and edge carries `tenant`, `source` (discovered · declared · seeded · synthetic · derived · simulated), `confidence`, `created_at`, `updated_at`, `version`, `valid_from` and `valid_to`.

### Edge types

| Area | Edge | Notes / properties |
|---|---|---|
| Org | Person `MEMBER_OF` Department · Department `PART_OF` Organisation | |
| Accountability | Person `OWNS` / `DEVELOPS` / `APPROVES_RISK_FOR` AISystem · Person `OWNS` Risk | Accountability only, never activity tracking |
| Technical | AISystem `RUNS_ON` AWSResource · AWSResource `ASSUMES` / `CALLS` AWSResource | |
| Model & data | AISystem `USES_MODEL` Model · Model `PROVIDED_BY` Provider · AISystem `PROCESSES` Dataset · Model `TRAINED_ON` Dataset | `PROCESSES {purpose: inference \| training \| retrieval}`, with `purpose` as the edge qualifier. `TRAINED_ON` is model lineage; `training` means this system itself runs training |
| Discovery | Candidate `DERIVED_FROM` AWSResource · Candidate `PROMOTED_TO` AISystem | *(added in §L review)* |
| Risk | AISystem `HAS_RISK` Risk · Risk `MITIGATED_BY` Control | |
| Obligations | Requirement `PART_OF` Framework \| Requirement | Parent may be a requirement, for hierarchy such as Art. 9 → 9(2)(a) *(§L)* |
| | Requirement `MAPS_TO` Control | `{strm, strength 1–10, rationale_type, rationale, sufficiency: full \| partial}`. `strength` and `sufficiency` are empty for `no_relationship` |
| | Requirement `APPLIES_TO` AISystem \| Organisation | `{role, rule_id, reason, in_force_from}`, with `role` as the edge qualifier. `in_force \| upcoming` is derived from `as_of`, not stored (D5) *(org target added §L)* |
| Assurance | ControlAssessment `ASSESSES` Control · ControlAssessment `SCOPED_TO` AISystem \| Organisation \| Provider | *(Provider scope added §L)* |
| | Person `ASSESSED` ControlAssessment | Named human verifier, required for L4 *(§L)* |
| | Evidence `SUPPORTS` ControlAssessment · Evidence `ABOUT` any node · Evidence `COLLECTED_FROM` AWSResource | `ABOUT` lets a DPA document describe a Provider *(§L)* |
| | Policy `IMPLEMENTS` Control | |
| Provenance | DiscoveryRun `OBSERVED` AWSResource · ChangeEvent `AFFECTS` AWSResource | |

> **Key modelling choice: status lives on `ControlAssessment`, not on `Control`.** "Is human oversight implemented?" has a different answer for each system. A `Control` is a reusable definition. A `ControlAssessment` is *control × scope* and holds `status`, `assurance_level`, `method`, `assessed_at` and `assessor`. Keeping these apart is what lets the data distinguish **mapping**, **implementing** and **demonstrating**, not just the UI.

**Control scope inheritance:** `Control.scope_level ∈ {organisation, system, provider}`. When a system-level question asks about an organisation-level control (for example the AI policy or AI literacy), the engine resolves it to the organisation's ControlAssessment and shows it as *inherited*. Provider-level controls resolve through system → model → provider, and to *Not applicable* only when every model of the system is known to be in-house (D13). A system with no recorded model, or a third-party model with no `PROVIDED_BY`, is a gap: *provider unknown*.

### Core traversals

| Question | Traversal |
|---|---|
| What applies to system S, and what proves it? | `{S, Org} ←APPLIES_TO– Req –MAPS_TO→ Ctl ←ASSESSES– CA(scope by Control.scope_level: S, Org or Provider) ←SUPPORTS– Evidence`. A control with no CA or evidence still returns a row, because gaps are findings |
| Impact of an incident at provider P | `P ←PROVIDED_BY– Model ←USES_MODEL– AISystem → {owners, risks, applicable requirements, provider-scoped CAs}` (BFS, depth ≤ 3) |
| Crosswalk: requirement R in framework A → framework B | `R –MAPS_TO→ Ctl ←MAPS_TO– R′ (PART_OF* fw B)`, composed STRM (§F) |
| Evidence made stale by a change | `ChangeEvent –AFFECTS→ Resource ←COLLECTED_FROM– Evidence –SUPPORTS→ CA`, only where `Evidence.collected_at < ChangeEvent.detected_at` |
| Audit trail | `Req → Ctl → CA → Evidence` (with hashes, collector, `ASSESSED` person) |

## F. Framework crosswalk (hub and spoke)

- **Hub:** the *Verity Control Library*, about 25–35 controls (`VC-001…`) written in our own words. Each has `kind ∈ {technical, organisational, legal_documentary}`, `automatable: bool` and `scope_level`. Only technical controls may be automatable.
- **Spokes:** each framework requirement maps to hub controls with:
  - an STRM type: `equal` · `subset_of` · `superset_of` · `intersects_with` · `no_relationship`
  - a strength from 1 to 10 (empty for `no_relationship`)
  - a rationale type: syntactic · semantic · functional
  - a written rationale
  - a `sufficiency` flag (empty for `no_relationship`)
- **Why a hub, not pairwise mappings:** pairwise mapping of 4 frameworks needs 6 mapping sets, and that number grows as N² while errors compound. A hub needs only N sets. Cross-framework links are **derived** by composing two spokes. Each one is labelled "related via VC-xxx", carries **no STRM type**, shows both spokes, takes the weaker of the two strengths, and `no_relationship` never composes. The Secure Controls Framework uses the same approach.
- **When a requirement counts as satisfied:**
  - **Satisfied:** its `sufficiency: full` set is **non-empty**, and every control in it has an `Implemented` ControlAssessment with assurance ≥ L2 from non-stale evidence.
  - **Not addressed:** no mappings at all.
  - **Partially addressed:** only partial mappings are met. This is never shown green.
- **Content rules:**
  - ISO entries contain the clause/control ID plus our own summary. No ISO text is reproduced.
  - EU AI Act and NIST entries may quote short excerpts with a citation.
  - Every requirement records `source_url`, `source_version` (for example "2024/1689 as amended by 2026/1744") and `last_verified`. It is not called `version`, which is the record revision counter on every node.
  - Obligation dates are data.
- **MVP content:** about 35 requirements, roughly 8–12 per instrument, chosen so they cover the three use cases.

## G. Evidence and assurance

**Evidence nodes are immutable.** Each holds:
- `kind`: config_snapshot · automated_test · usage_record · attestation · document_ref
- `subject`: the node it is about, matched by an `ABOUT` edge
- `collector`: `crawler@<ver>`, `cli@<ver>` or `person:<id>`
- `collected_at` and `valid_until`
- `content`: inline JSON up to a cap of 16 KB (D14, [ADR 0014](adr/0014-m2-measurements-and-evidence-cap.md)), *or* `content_ref` pointing to a git-versioned file under `evidence/`
- `sha256`

Re-collecting evidence creates a new node and never overwrites the old one.

**Freshness:**

| State | Meaning |
|---|---|
| fresh | Within `valid_until` and not invalidated |
| expiring | 7 days or less until `valid_until` |
| stale | Past `valid_until`, or collected before a `ChangeEvent` detected on its resource |

**Assurance ladder** (a separate field from implementation status):

| Level | Meaning |
|---|---|
| L0 Inferred | An applicability rule says the control applies |
| L1 Declared | A manifest or attestation claims it |
| L2 Evidenced | An artefact has been collected |
| L3 Tested | An automated check passed |
| L4 Verified | A named person signed off (`ASSESSED` edge) |

**Implementation status:** Implemented · Partially implemented · Not implemented · Not assessed · Not applicable.

**Guardrail:** automated checks can raise only controls with `automatable: true`. Organisational and legal controls are capped at *Partially implemented / L2* until an L4 human verification exists. **An AWS configuration check alone can never make an obligation green.**

_Later:_ a per-control hash chain, where each Evidence node stores the previous one's hash, to make tampering evident.

## H. Persistence: DynamoDB single-table design

**Table `verity-graph`:** provisioned capacity, Standard table class, auto-scaling off. Capacity is split as table 15 RCU/15 WCU and GSI1 10/10, which totals 25/25 and stays inside the Always Free allowance.

| Item | PK | SK |
|---|---|---|
| Node | `T#{tenant}#N#{id}` | `META` |
| Outgoing edge | `T#{tenant}#N#{src}` | `E#{type}#{dst}[#{qualifier}]` |
| Reverse edge (mirror) | `T#{tenant}#N#{dst}` | `R#{type}#{src}[#{qualifier}]` |
| Node history | `T#{tenant}#N#{id}` | `H#{iso_ts}#{version}` (version zero-padded to 10 digits, so keys sort numerically) |
| Usage record | `T#{tenant}#N#{system}` | `U#{iso_ts}#{usage_id}` |

- The qualifier is `role` on `APPLIES_TO` and `purpose` on `PROCESSES`; other edge types have none ([ADR 0012](adr/0012-graph-schema-refinements.md)).
- Every item holds the whole record as a JSON string in `doc`. Evidence has no `H#` items, because it never changes ([ADR 0013](adr/0013-dynamodb-write-model.md)).
- `E#` and `R#` are written together in one transaction, as are `META` and `H#`.
- **GSI1** (`GSI1PK=T#{tenant}#TYPE#{type}`, `GSI1SK=id`) lists nodes by type. It holds keys only and is eventually consistent.
- Reverse lookups use the mirrored `R#` items instead of a second GSI, which keeps the design inside the 25-unit capacity budget.
- **Repository pattern:** the `GraphRepository` protocol exposes `get_node`, `upsert_node`, `upsert_edge`, `neighbors(direction, type)`, `nodes_by_type`, `history`, `append_usage`, `usage_records`, `close_edge` and `load_graph(as_of) → networkx.MultiDiGraph`. Each repository is bound to one tenant. `as_of` uses the node versions held at that time.
  - Implementations are `InMemoryRepository` (tests and local development) and `DynamoDBRepository`.
  - A future `Neo4jRepository` or `NeptuneRepository` would plug into the same interface. That is the migration path off DynamoDB.
- **Traversal** happens in memory with NetworkX. The graph is hundreds to low thousands of items, so loading it whole is cheap. Daily evidence could take it far past that ([ADR 0014](adr/0014-m2-measurements-and-evidence-cap.md)), and M6 decides how to limit it.
- **History:** edges are soft-deleted by setting `valid_to`. A reopened edge keeps its earlier periods in `closed_intervals`. Nodes keep append-only `H#` versions. Together these support "what did system S look like on date D?" queries.

## I. Interfaces

- **CLI:**
  - `verity seed`: load content and organisation YAML
  - `verity crawl [--local]`
  - `verity assess`
  - `verity attest <control> <scope> --by <person>`: scaffolds a YAML file under `content/decisions/` for review; it never writes to the graph
  - `verity export`: write the redacted snapshot
- **Crawler Lambda:** event `{ "mode": "full" | "incremental" }`, triggered by the schedule or a manual invoke.
- **Snapshot contract:** `snapshot.schema.json` is generated from the pydantic models, and the TS types are generated from that schema, so the frontend and backend cannot drift.
- **Governance as code:** human decisions live as reviewed YAML under `content/decisions/` (risk-tier confirmations, attestations, risk treatments). The approving pull request is the approval record. See [ADR 0008](adr/0008-governance-as-code.md).
- **No public API in the MVP.** _Later:_ an admin write API on a Function URL with `AWS_IAM` auth.

## J. Frontend and security

**Frontend:**
- **Stack:** Vite + React + TS, React Router (hash routing for GitHub Pages), shadcn/ui + Tailwind, TanStack Table, Recharts, Cytoscape.js (fcose layout), MiniSearch.
- **Screens:**
  1. Overview
  2. AI Registry, with the Candidates inbox and a System profile (tabs: summary · components · data · risks · obligations · controls & evidence · history)
  3. Risk register
  4. Crosswalk explorer
  5. Controls & evidence, showing the assurance ladder
  6. Graph explorer, with an "impact of…" mode
- Every view shows provenance badges and the snapshot timestamp.

**Security:**

| Area | Measure |
|---|---|
| Account | MFA on root, and root is never used day to day. An admin IAM user with MFA. IAM Identity Center is not available on the Free plan, so we use the `aws login` flow, which is verified to work ✅. The CLI now uses the IAM user `rohpod` with default region eu-north-1. That user has no permissions yet; M3 grants them before any apply. |
| Workloads | One least-privilege role per Lambda. The crawler is read-only except for its own table. |
| Abuse limits | mock-openai's Function URL uses `AWS_IAM` auth ([ADR 0009](adr/0009-mock-openai-iam-auth.md)). Reserved concurrency is not available: the account limit is 10 and AWS requires 100 unreserved. mock-bedrock can only be invoked via IAM. The Free plan cannot bill, which caps the worst case. |
| Data | Synthetic data only. Env var values are discarded on receipt and never stored or logged. |
| Public snapshot | The export redacts the account ID (`000000000000`) and strips function URLs. |
| Repository | Secret scanning, Dependabot, branch protection on `main`. CI holds no AWS credentials. |
| Developer guardrail | A Claude Code project hook asks for confirmation before `terraform/tofu apply` and mutating `aws` commands. |

## K. Decision log

| ADR | Decision |
|---|---|
| [0001](adr/0001-free-plan-single-region.md) | AWS Free plan, single region (region superseded by 0011) |
| [0002](adr/0002-terraform-no-s3.md) | Terraform/OpenTofu with direct Lambda uploads, no S3 |
| [0003](adr/0003-dynamodb-graph-repository.md) | DynamoDB single-table graph + NetworkX behind a repository interface |
| [0004](adr/0004-hub-and-spoke-strm-crosswalk.md) | Hub-and-spoke crosswalk with NIST IR 8477 STRM |
| [0005](adr/0005-control-assessment-assurance-ladder.md) | ControlAssessment + assurance ladder |
| [0006](adr/0006-static-snapshot-demo.md) | Public demo as a redacted static snapshot |
| [0007](adr/0007-mock-only-ai-providers.md) | Bedrock/OpenAI mock-only behind adapter SDK |
| [0008](adr/0008-governance-as-code.md) | Human governance decisions as code |
| [0009](adr/0009-mock-openai-iam-auth.md) | mock-openai uses an `AWS_IAM` Function URL; reserved concurrency dropped |
| [0010](adr/0010-assessment-and-crosswalk-semantics.md) | Assessment and crosswalk semantics |
| [0011](adr/0011-region-eu-north-1.md) | Single region is eu-north-1 |
| [0012](adr/0012-graph-schema-refinements.md) | Graph schema refinements: edge qualifier, closed intervals, tenant is the organisation, staleness cutoff |
| [0013](adr/0013-dynamodb-write-model.md) | DynamoDB write model: transactions, JSON records, version checks |
| [0014](adr/0014-m2-measurements-and-evidence-cap.md) | M2 results: throttling retries, measured costs, 16 KB inline evidence cap |

## L. Schema validation walkthrough

I traced each core traversal (§E) against the three use cases. Six gaps came out of this, and each fix is already reflected in §E.

1. **Org-level obligations.** EU AI Act Art. 4 (AI literacy) and ISO 42001's AI policy apply to the *organisation*, not to a single system. → `APPLIES_TO` now also targets `Organisation`, and `Control.scope_level` enables **inheritance**: system views show org-level controls as inherited.
2. **Vendor evidence.** Contract Insights' "no DPA with the provider" gap has nowhere to attach, because a DPA is about a `Provider`, not an AWS resource. → Added the `Evidence ABOUT <any node>` edge and allowed `ControlAssessment SCOPED_TO Provider`.
3. **In-house models.** Talent Screening's model has no external provider, so the provider-impact traversal broke on it. → Added `Model.origin`; `PROVIDED_BY` applies to third-party models only.
4. **Requirement granularity.** Some mappings need sub-clauses (for example Art. 9(2)(a)), not whole articles. → `PART_OF` can now point to a parent `Requirement`.
5. **Accountability for verification.** L4 "Verified" needs a navigable *who*. Before this fix it was only a string on the Evidence node. → Added the `Person ASSESSED ControlAssessment` edge.
6. **Candidate lifecycle.** There was no way to trace a promoted registry entry back to the resource that triggered it. → Added `Candidate DERIVED_FROM AWSResource` and `PROMOTED_TO AISystem`.

**Result:** all five traversals resolve for all three use cases using only the node and edge types above. M1 re-checked this with executable tests in `tests/graph/test_traversals.py`. Traversal 2 is correctly empty for Talent Screening (in-house model) and traversal 3 for the supplier clause (`no_relationship`).
