# Verity — Architecture

_Stage 3 deliverable · 2026-11-05 · Status: accepted, amended in Stage 4 (see [milestone plan](stage-4-milestones.md), [ADR 0009](adr/0009-mock-openai-iam-auth.md), [ADR 0010](adr/0010-assessment-and-crosswalk-semantics.md), [ADR 0012](adr/0012-graph-schema-refinements.md), [ADR 0013](adr/0013-dynamodb-write-model.md), [ADR 0021](adr/0021-m6-discovery.md), [ADR 0023](adr/0023-m7-demo-estate.md))._
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
                      discovery/  boundary · collectors · aws · signals · correlate · relate · usage · diff · persist · pipeline
                      rules/      applicability engine (system attributes × role × date → requirements)
                      assess/     control status, assurance level, requirement satisfaction, rollups
                      content/    YAML schema · loader · linter · seed (M4)
                      export/     snapshot builder + redaction
                      cli.py      `verity` command
  crawler/            handler.py — thin Lambda entrypoint
  sdk/verity_ai/      provider adapters (BedrockCompatible, OpenAICompatible) + usage telemetry; aws.py is the only module with boto3 (ADR 0023)
  apps/               support_assistant · talent_screening · contract_insights · shadow_summariser · invoice_renderer
  mocks/              mock_bedrock · mock_openai
  scripts/            build_lambdas.py: deterministic zips into .build/ (ADR 0023)
  content/            frameworks/ · controls.yaml · mappings/ · rules/ · org/ · manifests/ · decisions/ · fixtures/
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
| EU AI Act screening | Limited risk: Art. 50(1) transparency. Role: provider + deployer | **Annex III §4(a) employment → high-risk candidate.** Chapter III applies from **2 Dec 2027**, but the system was placed on the market in 2026, so under Art. 111(2) its duties show as **Conditional** until a significant design change ([ADR 0019](adr/0019-m5-rules-and-assessment.md)) | Minimal risk. Third-party / downstream-provider considerations |
| Governance story | Transparency, human handoff, logging | Bias, data governance, human oversight, technical documentation | Vendor risk, cross-border data transfer, confidentiality |
| Seeded finding | Role grants `bedrock:InvokeModel` (the permission Converse needs, [ADR 0022](adr/0022-m6-review-fixes.md)) but **no usage is observed**. This is a least-privilege finding; the permission is never exercised, in keeping with the mock-only rule | No bias-test evidence → gap | No DPA evidence for the provider → gap |

**Crawler test fixtures:**
- `shadow-summariser` has no tags and no manifest but has an `OPENAI_BASE_URL` env var. It must be classified *probable* and surface as a shadow-AI candidate. It really calls mock-openai through `OpenAICompatible` with `usage=None`, has no `verity_core` in its zip and writes no usage records, like a team that wired up a client and never registered the system ([ADR 0023](adr/0023-m7-demo-estate.md)).
- `invoice-renderer` is an ordinary function and must be classified *none*.

**Bundled data.** The help articles ship in the support assistant's zip (`HELP_ARTICLES_FILE`) and the invoice template in the invoice renderer's (`INVOICE_TEMPLATE`), because a second table is impossible at 25 of 25 capacity units and S3 is banned. App roles write usage records with `dynamodb:PutItem` only, limited by `dynamodb:LeadingKeys` to their own usage partition, which holds nothing else (D8, [ADR 0024](adr/0024-m7-review-fixes.md)). Every mock labels itself simulated: `additionalModelResponseFields: {"simulated": true}` and a `[SIMULATED]` reply for mock-bedrock, `system_fingerprint: "verity-mock"`, the `x-verity-simulated` header and a `[SIMULATED]` reply for mock-openai.

**Guards** ([ADR 0024](adr/0024-m7-review-fixes.md)). These were found by running the built zips' handlers against a local fake, and `tests/build/test_zip_handlers.py` keeps them true.
- **Telemetry has a time budget.** A usage write makes at most 2 attempts with 0.5 s to connect and 1 s to read, so it gives up within about 4 seconds. The model call's timeouts are 5 s per socket read, and a test pins the sums against every function's 10 s timeout. They bound a call that stalls, not a body that trickles in (a fake that dripped one took 12.3 s, accepted because the only server is our own mock), and cold start is not in them. A throttled write loses that usage record and logs `usage_write_failed`.
- **Apps never touch the root logger.** `LOG_LEVEL` sets the app's own logger and `verity_ai`'s. `verity_ai.aws` holds `botocore`, `boto3` and `urllib3` at `WARNING`, so a `DEBUG` run logs neither the customer's message nor the session token, even if Lambda sets the root level.
- **Adapters fail one way.** A redirect is not followed (the signed headers would reach an unchecked host), and a connection error, a dropped or truncated response, a timeout, a bad body, a response with no `usage` or a Lambda client error is an `AdapterError` holding no body.
- **Impossible input is refused, unusual input is flagged.** Talent Screening refuses a value outside `valid_ranges` and names the feature, never the value. A value outside `training_ranges` is ranked and listed in `outside_training_range`, because refusing it would turn away long careers: an age proxy.
- **The zips hold tracked files at locked versions,** and only the part of `verity_core` the two functions import. Build from a clean tree before deploying: an uncommitted edit to a tracked file still ships.

**Synthetic estate:** about 25 additional AI systems for the fictional **Kestrel Cloud Ltd**, with `source=synthetic` and no AWS resources, so posture charts have realistic volume. Every record in the UI carries a provenance badge: **Live-discovered · Declared · Synthetic**.

## D. Discovery crawler

The pipeline is a sequence of pure functions over plain data, so it can be unit-tested with `moto` and recorded fixtures. `crawl` reads the clock once, and `persist` is the only writer ([ADR 0021](adr/0021-m6-discovery.md)).

| # | Stage | What it does |
|---|---|---|
| 1 | Enumerate | `tag:GetResources`, `lambda:ListFunctions`, `iam:ListRoles`, `dynamodb:ListTables`, `ssm:GetParametersByPath(/verity/manifests)`. Resource Explorer `Search` is optional and uses the local index only, never Config-backed views. M6 builds this against `moto` only; the live read is M8. |
| 2 | Enrich | Function configuration (runtime, role, architecture). **Env var *names* only.** `ListFunctions` returns values too, so `boundary.py` discards them on receipt: never stored, never logged, and covered by a canary test. Tags. Inline and attached role policies. 12-digit account IDs in any kept string become `acct_` and 8 hex digits of their hash, so different accounts stay different (M9 replaces the digests on export). The Lambda description is scored but never stored. |
| 3 | Signal & score | Rules in `content/rules/ai_signals.yaml` combine signals into `ai_likelihood ∈ {declared, confirmed_usage, probable, possible, none}`. Every result stores the signals that fired, so the UI can explain *why*. Only Lambda functions are scored. |
| 4 | Correlate | The `ai:system-id` tag (a full ID such as `sys:talent-screening`) or a manifest links a resource to an `AISystem`. An unlinked function scored *probable* or *possible*, or one that names a system that does not exist, becomes a `Candidate` (the shadow-AI inbox). |
| 5 | Relate | `RUNS_ON` (system → function), `ASSUMES` (function → role) and `CALLS` (function → table or function, from the resource ARNs in the role's `Allow` statements; `Resource: "*"` makes no edge). The crawler creates no system → provider link: §E's path through Model stands. |
| 6 | Usage | `verity_ai` adapters write `U#` usage records (system, provider, model, timestamp, token estimate), labelled simulated. This is evidence of **third-party model calls** only: an in-house model has no provider, so Talent Screening writes none, and a failed write never fails the call, because it gives up within about 4 seconds ([ADR 0023](adr/0023-m7-demo-estate.md), [ADR 0024](adr/0024-m7-review-fixes.md)). They sit in `T#{tenant}#U#{system}`, a partition of their own (§H). CloudTrail `LookupEvents` is also queried for `bedrock.amazonaws.com`; the honest expected result is *none observed*. Capability without usage is the control VC-060 (below). |
| 7 | Diff | Config hashes are compared with the stored ones to produce `ChangeEvent`s. Evidence collected from a changed resource becomes **stale**. |
| 8 | Persist | Idempotent upserts with deterministic IDs, plus a `DiscoveryRun` node for provenance. |

**Signal ladder (summary):**

| Signal | Strength |
|---|---|
| Manifest or `ai:system-id` tag | declared |
| Usage records or CloudTrail AI events | confirmed_usage |
| IAM grants AI actions; AI-named env vars | probable |
| Name or description heuristics | possible |

The order is declared, confirmed_usage, probable, possible, none. The strongest wins and every signal that fired is stored, sorted. A function is exempt, scoring *none* with the signal `platform_component`, only if it has the `verity:component` tag **and** its name is in `platform_functions` in `ai_signals.yaml` (the mocks and the crawler); the tag alone does nothing. An IAM signal on a role counts for the function that assumes it. `ai_actions` is a list of real IAM actions (`bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream`, `bedrock:InvokeAgent`, `bedrock:InvokeInlineAgent`, `bedrock:InvokeFlow` and three `sagemaker:InvokeEndpoint` forms), each with the CloudTrail event names that prove a call to it. A statement grants one if an `Allow` statement's `Action` patterns match it, or a `NotAction` statement's do not. An env var name matches a vendor word as a whole `_`-separated part in any position. The `name` signal matches whole tokens, split on non-alphanumerics and at CamelCase, so `mail` and `maintenance` never match `ai`.

**Written on change only** ([ADR 0021](adr/0021-m6-discovery.md)). A resource gets a `config_snapshot` when it is new, its `config_hash` differs from its latest snapshot's, or that snapshot has 8 days or less to run (`EXPIRING_WITHIN` plus one). `OBSERVED` is written only for a new or changed resource, and `DiscoveryRun.summary` holds the per-run counts. Crawler evidence is valid for 30 days. Evidence over the 16 KB cap is summarised as `{truncated, config_hash, ai_actions, statement_count}`, never refused. A deleted resource is ended with `valid_to` and gets no ChangeEvent.

**Write order**, so a failed run is repaired by the next: the run, then each `ChangeEvent` and `AFFECTS` before the node changes, resources, `RUNS_ON`/`ASSUMES`/`CALLS`, Candidates, Evidence, the ending of resources not seen, and finally the run again with `finished_at`. The crawler writes only `AWSResource`, `Candidate`, `DiscoveryRun`, `ChangeEvent` and `Evidence`, and never an `AISystem`.

**Candidate lifecycle.** Created when a function qualifies, ended with `valid_to` when it stops or its resource goes. If its resource becomes linked to a system it **stays open** with `PROMOTED_TO`, because an open edge to an ended node is refused. If it qualifies again, the `PROMOTED_TO` edge is closed and the finding returns. An unlinked function that scores `confirmed_usage` is a Candidate too.

**Capability without usage (VC-060).** For each system that runs on a role, the crawler writes one `automated_test` Evidence with `control: ctl:VC-060`, the system as `scope`, `outcome`, `granted`, `unused`, `unverifiable` and `roles_unseen`. The outcome is `fail` if a granted action has none of its proving CloudTrail events for the role that grants it (a `Converse` event proves `bedrock:InvokeModel`). It is `inconclusive` if a granted action has no events history can show, or a function of the system has a role the crawler cannot see; the assessor then gives Not assessed. Otherwise it is `pass`. Only CloudTrail counts, never `U#` records, because the demo's usage comes from a mock. Only `Allow` statements grant, `NotAction` included, so a broad role fails; `Deny` is not subtracted. Evidence is also written again when the latest is stale from a stored ChangeEvent, so a crashed run is repaired by the next ([ADR 0022](adr/0022-m6-review-fixes.md)). No other control is raised by the crawler.

**IAM:** a custom least-privilege policy, rather than the broader AWS-managed `SecurityAudit`. It allows exactly these read actions and no others:

`lambda:ListFunctions` · `tag:GetResources` · `iam:ListRoles` · `iam:ListRolePolicies` · `iam:GetRolePolicy` · `iam:ListAttachedRolePolicies` · `iam:GetPolicy` · `iam:GetPolicyVersion` · `dynamodb:ListTables` · `ssm:GetParametersByPath` · `cloudtrail:LookupEvents`

It deliberately excludes `lambda:GetFunction` (which would allow code download), and its only write access is to `verity-graph`. A test records every operation the collector calls and fails on any other.

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
- `AWSResource` carries `ai_likelihood` and `signals` for Lambda functions, and `DiscoveryRun` carries `summary`, a map of counts ([ADR 0021](adr/0021-m6-discovery.md)).
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
| | Requirement `APPLIES_TO` AISystem \| Organisation | `{role, rule_id, reason, in_force_from, condition}`, with `role` as the edge qualifier. `in_force \| upcoming \| conditional` is derived from `as_of`, not stored (D5) *(org target added §L)* |
| Assurance | ControlAssessment `ASSESSES` Control · ControlAssessment `SCOPED_TO` AISystem \| Organisation \| Provider | *(Provider scope added §L)* |
| | Person `ASSESSED` ControlAssessment | Named human verifier, required for L4 *(§L)* |
| | Evidence `SUPPORTS` ControlAssessment · Evidence `ABOUT` any node · Evidence `COLLECTED_FROM` AWSResource | `ABOUT` lets a DPA document describe a Provider *(§L)* |
| | Policy `IMPLEMENTS` Control | |
| Provenance | DiscoveryRun `OBSERVED` AWSResource · ChangeEvent `AFFECTS` AWSResource | |

> **Key modelling choice: status lives on `ControlAssessment`, not on `Control`.** "Is human oversight implemented?" has a different answer for each system. A `Control` is a reusable definition. A `ControlAssessment` is *control × scope* and holds `status`, `assurance_level`, `method`, `assessed_at` and `assessor`. Keeping these apart is what lets the data distinguish **mapping**, **implementing** and **demonstrating**, not just the UI.

**Control scope inheritance:** `Control.scope_level ∈ {organisation, system, provider}`. When a system-level question asks about an organisation-level control (for example the AI policy or AI literacy), the engine resolves it to the organisation's ControlAssessment and shows it as *inherited*. Provider-level controls resolve through system → model → provider, and to *Not applicable* only when every model of the system is known to be in-house (D13). A system with no recorded model, or a third-party model with no `PROVIDED_BY`, is a gap: *provider unknown*.

### Applicability

`verity assess` derives `APPLIES_TO` edges from `content/rules/applicability.yaml`, the obligation dates, each system's facts and the decisions in force at `as_of` ([ADR 0019](adr/0019-m5-rules-and-assessment.md), [ADR 0020](adr/0020-m5-review-fixes.md)). The rules are our reading of the law, not legal advice. All are EU AI Act rules except the last.

| Rule | Requirements | Target and role | When | Date |
|---|---|---|---|---|
| `eu-literacy` | Art. 4 | Organisation, one edge for each of provider and deployer that any system holds | Always | `euaia-chapters-1-2` |
| `eu-disclosure` | Art. 50(1) | System, provider | `interacts_with_people` | `euaia-general` |
| `eu-marking` | Art. 50(2) | System, provider | `generates_synthetic_content` | `euaia-art50-2-legacy` if placed on the market before `euaia-general`, otherwise `euaia-general` |
| `eu-high-risk-provider` | Art. 9, 10, 11, 12, 13, 14, 25(4), with the sub-clauses held | System, provider | High-risk | `euaia-high-risk-annex-iii`, with Art. 111(2) |
| `eu-high-risk-deployer` | Art. 26, 26(2), 26(7) | System, deployer | High-risk | `euaia-high-risk-annex-iii`, with Art. 111(2) |
| `adopted-frameworks` | Every leaf of NIST AI RMF, ISO 42001 and ISO 27001 | Organisation, any role | Always, because Kestrel adopted them | None |

**Risk tier.** A `risk_tier` decision counts only while in force: unsuperseded, collected by `as_of` and not past `valid_until`. The latest one in force wins. Rules apply to *Confirmed* and *Candidate*.

| Decisions at `as_of` | Annex III domain? | Tier | Finding |
|---|---|---|---|
| In force, `high_risk` | Any | Confirmed | None |
| In force, `not_high_risk` | Any | Not high-risk | None |
| None, or all superseded | Yes | Candidate | `risk_tier_unconfirmed`, high |
| None, or all superseded | No | Not high-risk | None |
| Only expired, either tier | Yes | Candidate | `risk_tier_expired`, high |
| Only expired, `high_risk` | No | Candidate | `risk_tier_expired`, high |
| Only expired, `not_high_risk` | No | Not high-risk | `risk_tier_expired`, medium |

**Art. 111(2).** A high-risk system placed on the market before the Annex III date is in scope only after a significant change in its design.
- `significant_change_on` empty or before that date: the edge has the Annex III date as `in_force_from` and `condition: legacy_significant_change`.
- `significant_change_on` on or after that date: the edge starts on the change date, with no condition.
- "Put into service" and the 2 August 2030 deadline for systems intended for public authorities are not modelled ([ADR 0020](adr/0020-m5-review-fixes.md)).

**Status**, derived on read: *Conditional* if the edge has a `condition`, whatever the date. Otherwise *Upcoming* before `in_force_from`, else *In force*. No date means *In force*.

**Unknown facts.** Left out means unknown, not false. No rule applies on an unknown fact, and `unknown_fact` asks a person to record it.

| Fact missing | Effect | Severity |
|---|---|---|
| `roles` | No system rule applies | High |
| `use_domains` | No Annex III candidate. Exempt while a risk-tier decision is in force | High |
| A fact a rule reads, such as `interacts_with_people` | That rule does not apply | Medium |
| `first_placed_on_market` | The exception: the rule applies on the non-legacy path | Medium |

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
  - a strength from 1 to 10 (empty for `no_relationship`). This is a Verity convention taken from the Secure Controls Framework; NIST IR 8477 does not define one ([ADR 0017](adr/0017-m4-content-semantics.md))
  - a direction: the requirement is concept A and the control is concept B, so `subset_of` means the control covers the whole requirement and more
  - a rationale type: syntactic · semantic · functional
  - a written rationale
  - a `sufficiency` flag (empty for `no_relationship`)
- **Why a hub, not pairwise mappings:** pairwise mapping of 4 frameworks needs 6 mapping sets, and that number grows as N² while errors compound. A hub needs only N sets. Cross-framework links are **derived** by composing two spokes. Each one is labelled "related via VC-xxx", carries **no STRM type**, shows both spokes, takes the weaker of the two strengths, and `no_relationship` never composes. The Secure Controls Framework uses the same approach.
- **When a requirement counts as satisfied** ([ADR 0019](adr/0019-m5-rules-and-assessment.md)). A control is *met* if its assessment is Implemented at L2 or above from non-stale evidence. Every provider target must be met, and *provider unknown* is unmet. The first matching row wins:

  | # | Condition | Status | Reason |
  |---|---|---|---|
  | 1 | Every target resolves to an in-house model | Not applicable | `in_house_only` |
  | 2 | A parent with no mappings of its own | Partially addressed if any child is Satisfied or Partially addressed, else Not met. Never Satisfied | `rollup` |
  | 3 | No usable mapping | Not addressed | `never_mapped`, or `reviewed_no_control` for `no_relationship` |
  | 4 | Its `sufficiency: full` set is non-empty, every control in it is met, and at least one is non-automatable or at L4 | Satisfied | |
  | 5 | That set is non-empty and all met, but the automated-only guardrail stops it | Partially addressed | `automated_only` |
  | 6 | At least one mapped control is met | Partially addressed | `partial_only` |
  | 7 | Nothing is met | Not met | |

  *Partially addressed* is never shown green. A status resting on a simulated sign-off carries `simulated: true`, and the CLI counts those apart.
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

**Assessing a control** ([ADR 0019](adr/0019-m5-rules-and-assessment.md)). Usable evidence names the control and the scope, was collected by `as_of`, is not stale and is not a superseded decision. The first matching row wins, using the latest evidence of that kind:

| # | Evidence | Status | Level |
|---|---|---|---|
| 1 | Automatable control, automated test that failed | Not implemented | L3 |
| 2 | Verification decision by a person | As decided | L4 |
| 3 | Automatable control, automated test that passed | Implemented | L3 |
| 4 | `document_ref` | Partially implemented | L2 |
| 5 | Automatable control, automated `config_snapshot` | Partially implemented | L2 |
| 6 | Attestation decision saying `not_implemented` | Not implemented | L1 |
| 7 | Any other attestation decision | Partially implemented | L1 |
| 8 | Anything else, or nothing | Not assessed | L0 |

An open assessment that a run no longer produces is ended with `valid_to`, and reopened if a later run produces it ([ADR 0020](adr/0020-m5-review-fixes.md)).

**Guardrail:** automated checks can raise only controls with `automatable: true`. Organisational and legal controls are capped at *Partially implemented / L2* until an L4 human verification exists. **An AWS configuration check alone can never make an obligation green.**

**Decisions** are human sign-offs held as YAML under `content/decisions/`, and seeded as Evidence with inline content and an `ABOUT` edge ([ADR 0019](adr/0019-m5-rules-and-assessment.md), [ADR 0020](adr/0020-m5-review-fixes.md)).
- **Kinds:** `risk_tier`, `verification`, `attestation`, `document` and `revocation`. A revocation names no control, so it can never count as an assessment.
- **Immutable once seeded.** `verity seed` refuses a stored decision that was edited (`decision_edited`) or removed (`decision_removed`). A change is a new decision naming the old one in `supersedes`.
- **Supersession is time-aware and permanent.** A decision is superseded at `as_of` if a decision collected by then names it. The new decision's own expiry does not bring the old one back.
- **Lint refuses** a target that does not exist (`decision_unknown_supersedes`), a target with a different subject, a later date, or a loop (`decision_supersedes_mismatch`), two unsuperseded decisions with the same kind, subject, control and date (`decision_conflict`, which revocations are exempt from), and a statement still holding a `TODO` (`decision_todo`).

**Findings** are derived on read and never stored (D5). They sort by severity, then code, subject and message.

| Code | Raised when | Severity |
|---|---|---|
| `control_not_met` | A control's status is Not implemented | High |
| `no_evidence` | A control's status is Not assessed | High if it backs an in-force or conditional requirement of a framework with `binding: true`, else medium |
| `provider_unknown` | A control needs a provider and none is recorded. Never *Not applicable* | High |
| `risk_tier_unconfirmed` | A candidate with no decision (§E) | High |
| `risk_tier_expired` | Only expired risk-tier decisions remain (§E) | High, or medium if the system stays not high-risk |
| `unknown_fact` | A fact a rule needs is missing (§E) | High for `roles` and `use_domains`, else medium |
| `no_owner` | A system has no `OWNS` edge | Medium |
| `evidence_expiring` | The deciding evidence is expiring | Low |
| `conditional_obligation` | One per system with a conditional edge | Low |
| `shadow_ai_candidate` | An open Candidate has no open `PROMOTED_TO` edge. The subject is the Candidate | High for `declared`, `confirmed_usage` and `probable`; medium for `possible` |

`binding` is a fact on `Framework`: true for the EU AI Act, false for the standards Kestrel adopted by choice ([ADR 0020](adr/0020-m5-review-fixes.md)).

_Later:_ a per-control hash chain, where each Evidence node stores the previous one's hash, to make tampering evident.

## H. Persistence: DynamoDB single-table design

**Table `verity-graph`:** provisioned capacity, Standard table class, auto-scaling off. Capacity is split as table 15 RCU/15 WCU and GSI1 10/10, which totals 25/25 and stays inside the Always Free allowance.

| Item | PK | SK |
|---|---|---|
| Node | `T#{tenant}#N#{id}` | `META` |
| Outgoing edge | `T#{tenant}#N#{src}` | `E#{type}#{dst}[#{qualifier}]` |
| Reverse edge (mirror) | `T#{tenant}#N#{dst}` | `R#{type}#{src}[#{qualifier}]` |
| Node history | `T#{tenant}#N#{id}` | `H#{iso_ts}#{version}` (version zero-padded to 10 digits, so keys sort numerically) |
| Usage record | `T#{tenant}#U#{system}` | `U#{iso_ts}#{usage_id}` |

- The qualifier is `role` on `APPLIES_TO` and `purpose` on `PROCESSES`; other edge types have none ([ADR 0012](adr/0012-graph-schema-refinements.md)).
- Usage records have their own partition because `dynamodb:LeadingKeys` limits the partition key and IAM has no matching condition for a sort key. An app role's condition names `T#kestrel#U#sys:<system>`, so the worst it can do is damage its own simulated usage ([ADR 0024](adr/0024-m7-review-fixes.md)).
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
  - `verity seed`: load content and organisation YAML. It refuses an edited or removed decision
  - `verity crawl --local [--fixture PATH] [--verbose]`: crawl a recorded fixture (default `content/fixtures/crawl/estate.json`) into a fresh in-memory graph, then assess it. It prints that the data is simulated and nothing was read from AWS, each function with its likelihood and signals, the Candidates, what was written, and the assessment. Without `--local` it is refused until the deployed crawler exists (M8). Only `full` crawls exist
  - `verity lint`: check the content
  - `verity assess [--as-of DATE] [--system ID] [--target memory|dynamodb] [--verbose]`: derive applicability and assess the controls. With no date, or today's, it assesses as of now, so a crawl's evidence from earlier in the day is seen; another date is the start of that day. Memory (the default) seeds and assesses a fresh graph and writes nothing to AWS. It prints counts, lists every high finding and counts the rest by code; `--verbose` lists them all. An unknown `--system` is refused
  - `verity attest <control> <scope> --by <person>`: scaffolds a YAML file under `content/decisions/` for review; it never writes to the graph
  - `verity export --local [--as-of WHEN] [--out PATH] [--fixture PATH]` | `verity export --check FILE`: write the redacted snapshot of the recorded fixture, crawled and assessed in memory, reading nothing from AWS (default `.build/snapshot.json`), or scan an existing file. It refuses a graph whose stored assessments are not the ones an assessment at `--as-of` would give, adds the findings and the precomputed obligations, provider impact and crosswalk, and writes only if the independent scan is clean ([ADR 0029](adr/0029-m9-snapshot-export.md)). Without `--local` it reads the live graph through `GraphRepository.load_graph()`, read-only, as of now (`--as-of` and `--fixture` are refused), and looks up the commit that introduced each decision file, refusing if one is missing (ADR 0029, decisions 1 and 9). It has not yet been run against the real table
- **Crawler Lambda (M8):** event `{ "mode": "full" | "incremental" }`, triggered by the schedule or a manual invoke. Only `full` is built ([ADR 0021](adr/0021-m6-discovery.md)).
- **Snapshot contract:** `web/generated/snapshot.schema.json` is generated from the pydantic models, and `web/generated/snapshot.ts` from that schema (`uv run python scripts/generate_snapshot_contract.py`), so the frontend and backend cannot drift. CI regenerates both and fails on a difference ([ADR 0029](adr/0029-m9-snapshot-export.md)).
- **Governance as code:** human decisions live as reviewed YAML under `content/decisions/` (§G). The approving pull request is the approval record. Risk treatment decisions are deferred ([ADR 0019](adr/0019-m5-rules-and-assessment.md)). See [ADR 0008](adr/0008-governance-as-code.md).
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
| Account | MFA on root, and root is never used day to day. An admin IAM user with MFA. IAM Identity Center is not available on the Free plan, so we use the `aws login` flow, which is verified to work ✅. The CLI uses the IAM user `rohpod` with default region eu-north-1. It has `AdministratorAccess` plus the `verity-never-use` deny policy ([ADR 0015](adr/0015-account-baseline.md)). |
| Workloads | One least-privilege role per Lambda. The crawler is read-only except for its own table. |
| Abuse limits | mock-openai's Function URL uses `AWS_IAM` auth ([ADR 0009](adr/0009-mock-openai-iam-auth.md)). Reserved concurrency is not available: the account limit is 10 and AWS requires 100 unreserved. mock-bedrock can only be invoked via IAM. The Free plan cannot bill, which caps the worst case. |
| Data | Synthetic data only. Env var values are discarded on receipt and never stored or logged. |
| Public snapshot | The export redacts the account ID (`000000000000`), withholds config hashes, rebuilds the hashes of redacted Evidence, lists Evidence content keys and tags, and scans in memory before anything is written ([ADR 0029](adr/0029-m9-snapshot-export.md), [ADR 0030](adr/0030-m9-redaction-review.md)). |
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
| [0015](adr/0015-account-baseline.md) | Account baseline: identity outside OpenTofu, deny policy, `credential_process`, budget excludes credits |
| [0016](adr/0016-m3-live-results.md) | M3 live results: capacity, GSI delay, how throttling is reported |
| [0017](adr/0017-m4-content-semantics.md) | M4 content semantics: mapping direction, strength convention, `full` sufficiency, obligation dates, ISO provenance |
| [0018](adr/0018-unread-standards.md) | Mappings from a standard nobody read claim only an overlap, so ISO requirements never show as Satisfied |
| [0019](adr/0019-m5-rules-and-assessment.md) | M5 rules and assessment: automated-only guardrail, Art. 111(2) conditional edges, high-risk candidates, decisions as Evidence, Not met |
| [0020](adr/0020-m5-review-fixes.md) | M5 review fixes: immutable decisions with `supersedes` and revocation, risk-tier expiry, unknown facts, severity from binding law, ended assessments |
| [0021](adr/0021-m6-discovery.md) | M6 discovery: evidence written on change, summarised over the cap, one cleaning boundary, VC-060 for unused permissions, Candidate lifecycle |
| [0022](adr/0022-m6-review-fixes.md) | M6 review fixes: concrete AI actions with proving events, an inconclusive VC-060 outcome, account digests, signal matching |
| [0023](adr/0023-m7-demo-estate.md) | M7 demo estate: layered `verity_ai`, corrected crawl fixture, runtime refusal of real endpoints, pure-Python talent model, deterministic zips |
| [0024](adr/0024-m7-review-fixes.md) | M7 review fixes: bounded telemetry, quiet AWS logs, a usage partition, reproducible zips, input ranges, a permissions boundary in M8 |
| [0025](adr/0025-m8-deploy-and-crawl.md) | M8 deploy: the crawler function, refused CloudTrail events prove nothing, simulator proof of the boundary, a real refused write, a fixture-shaped estate |
| [0026](adr/0026-m8-cold-start.md) | M8 cold start: bytecode in the zips that vendor packages, 512 MB for the apps that load pydantic and for the probe |
| [0028](adr/0028-m8-review.md) | M8 review: seed and assess time came from credential refreshes, the schedule and credit steps reworded, boundary claims matched to the evidence |
| [0029](adr/0029-m9-snapshot-export.md) | M9 export: listed public fields, rebuilt hashes for redacted Evidence, an independent fail-closed scanner, a generated contract |
| [0030](adr/0030-m9-redaction-review.md) | M9 redaction review: scan before writing, listed Evidence content and tags, a stricter scanner, a header that names what is not real |

## L. Schema validation walkthrough

I traced each core traversal (§E) against the three use cases. Six gaps came out of this, and each fix is already reflected in §E.

1. **Org-level obligations.** EU AI Act Art. 4 (AI literacy) and ISO 42001's AI policy apply to the *organisation*, not to a single system. → `APPLIES_TO` now also targets `Organisation`, and `Control.scope_level` enables **inheritance**: system views show org-level controls as inherited.
2. **Vendor evidence.** Contract Insights' "no DPA with the provider" gap has nowhere to attach, because a DPA is about a `Provider`, not an AWS resource. → Added the `Evidence ABOUT <any node>` edge and allowed `ControlAssessment SCOPED_TO Provider`.
3. **In-house models.** Talent Screening's model has no external provider, so the provider-impact traversal broke on it. → Added `Model.origin`; `PROVIDED_BY` applies to third-party models only.
4. **Requirement granularity.** Some mappings need sub-clauses (for example Art. 9(2)(a)), not whole articles. → `PART_OF` can now point to a parent `Requirement`.
5. **Accountability for verification.** L4 "Verified" needs a navigable *who*. Before this fix it was only a string on the Evidence node. → Added the `Person ASSESSED ControlAssessment` edge.
6. **Candidate lifecycle.** There was no way to trace a promoted registry entry back to the resource that triggered it. → Added `Candidate DERIVED_FROM AWSResource` and `PROMOTED_TO AISystem`.

**Result:** all five traversals resolve for all three use cases using only the node and edge types above. M1 re-checked this with executable tests in `tests/graph/test_traversals.py`. Traversal 2 is correctly empty for Talent Screening (in-house model) and traversal 3 for the supplier clause (`no_relationship`).
