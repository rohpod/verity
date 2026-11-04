# Stage 1 — Product Discovery

_2026-11-05 · Approved._ Some points here were later corrected by [Stage 2](stage-2-feasibility.md); those are marked **[Updated in Stage 2]**.

## 1. Product in one sentence
> "Show me every AI system we run on AWS, what it touches, which obligations apply to it, and whether we can prove we meet them — and tell me how confident we should be in that answer."

```
Discover → Register → Classify → Map obligations → Assess controls → Collect evidence → Remediate → Report
     ↑                                                                                    │
     └────────────── change detection (a resource changed → evidence becomes stale) ──────┘
```

The knowledge graph makes "what breaks if X changes?" a single traversal rather than a hand-written join.

## 2. Customer and personas
- **Customer:** a mid-size SaaS company with EU exposure. It builds some AI systems itself (EU AI Act *provider*) and buys others (*deployer*).
- **Personas:**
  - Compliance officer (primary user)
  - Engineering lead (owns AI systems; acts on remediation tasks)
  - Executive (read-only view of posture)

## 3. Gaps found in the initial idea
| # | Issue | Resolution |
|---|---|---|
| 1 | The EU AI Act's obligations depend on the organisation's **role** (provider, deployer, importer, distributor), not just on the application. | Test applicability per *(system, role)*. `role` is a property of `APPLIES_TO`. |
| 2 | Annex III high-risk classification is a legal conclusion, and the Art. 6(3) derogations require human judgement. | The tool **screens** (proposes a tier and shows its reasoning). A named human **confirms**. |
| 3 | Discovering infrastructure is not the same as discovering AI usage. Outbound calls to OpenAI are invisible to AWS control-plane APIs. | Score multiple signals into a confidence level. Manifests and tags are the primary signal. Usage telemetry comes from the adapter SDK. |
| 4 | An inventory is not a registry. | Discovered *candidates* are promoted into the curated *registry*. Unmatched candidates become shadow-AI findings. |
| 5 | Mapping, implementing and demonstrating are three different claims. | Model them as separate edges and statuses, with a separate assurance level. |
| 6 | Similar-sounding controls are not necessarily equivalent. | Use NIST IR 8477 STRM relationship types with a stated rationale. |
| 7 | ISO text is copyrighted. | Store clause/control IDs plus our own summaries only. |
| 8 | Regulatory dates are still moving. | Store dates as data, with their source and the date last verified. **[Updated in Stage 2: Reg. (EU) 2026/1744 moved the Annex III high-risk date to 2 Dec 2027.]** |
| 9 | Three apps produce too little data for a meaningful dashboard. | Add about 25 synthetic systems, each clearly labelled as synthetic. |
| 10 | People data could drift into surveillance. | Use fictional people only, and model accountability rather than activity. |
| 11 | A public demo backed by live AWS invites abuse and cost. | Publish a static snapshot instead. |
| 12 | The AWS free tier changed on 15 Jul 2025. | Design within Always Free limits only. **[Updated in Stage 2: confirmed Free-plan rules.]** |
| 13 | The original scope is too large for one person. | Cut the MVP to about 10 node types and 6 screens. |

## 4. Telling AI workloads from ordinary ones
| Signal | Source (read-only) | Strength |
|---|---|---|
| `ai:system-id` tag or manifest | Tagging API, SSM manifests | Declared |
| AI usage records, or CloudTrail AI events | Adapter telemetry, `LookupEvents` | Confirmed usage |
| IAM grants AI actions (e.g. `bedrock:*`) | IAM policies | Probable (capability is not proof of use) |
| AI-related env var *names* (`OPENAI_BASE_URL`, `MODEL_ID`) | Lambda configuration | Probable |
| Name or description heuristics | Resource metadata | Possible |

Scanning Lambda deployment code for AI libraries was considered and rejected. It requires `lambda:GetFunction`, which is a sensitive permission.

## 5. Feature ideas
- AI-BOM export (CycloneDX ML-BOM)
- Manifest-as-code, with a CI linter that checks manifests
- EU AI Act screening wizard: role → Art. 5 prohibitions → Annex III → Art. 6(3) → Art. 50
- Assurance ladder and evidence freshness
- Re-assessment triggered by changes to resources
- Graph impact analysis
- Regulatory timeline
- Third-party AI provider profiles (vendor risk)
- Audit package export
- Model and system cards generated from the graph
- Exceptions and risk acceptance, each with an expiry date

## 6. Differentiators vs Vanta and Drata
Both platforms already support ISO 42001, so "we support 42001" is not a differentiator. These are:
1. AI-native discovery that explains how confident it is and why.
2. A crosswalk typed with STRM relationships, so mappings show *how much* one requirement covers another, not just a tick.
3. Assurance levels on every claim, instead of a single green tick.
4. Graph-based impact analysis across people, systems, models, providers and obligations.
5. EU AI Act applicability that is aware of both role and date.
6. Manifest-as-code plus drift detection.

## 7. MVP scope
**In scope:**
- 3 AI apps deployed with infrastructure-as-code (with simulated inference where needed), plus 2 crawler test fixtures
- A read-only discovery crawler with confidence scoring and promotion of candidates into the registry
- A knowledge graph stored in DynamoDB
- About 35 curated requirements across the 4 instruments, mapped with STRM types
- 6 screens
- A static public demo

**Later:** remediation workflow, audit export, screening wizard, AI-BOM, multi-tenancy and authentication.

## 8. Naming
Candidates considered: Provenant, Assay, Cartograph AI, Attestly, Tessera, Aegis42. **The owner chose _Verity_** (from the Latin *veritas*, "truth", which suits a tool for evidence-backed claims).
