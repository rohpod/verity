# Stage 2 — Technical Feasibility Report
_Researched 2026-11-05. Status key: ✅ verified on an official source · 🟡 verified on a secondary source only · ❓ still unverified (re-check at implementation time)._

## 0. Headline findings
1. **The Free plan can't bill you.** It's the strongest zero-cost guarantee available. AWS: "You will not incur any charges during this period until you upgrade to a paid account plan." ✅ The real risk is *credit burn*, which ends the plan early, not a bill.
2. **The live AWS environment has a hard expiry.** The plan ends after **6 months or when credits are used up, whichever comes first** ✅. After that you have 90 days to upgrade, then the account and its data are deleted 🟡. → Everything must be IaC-rebuildable, and the GitHub Pages snapshot is the permanent artefact.
3. **Bedrock and SageMaker *are* available on the Free plan** ✅, funded by credits. This corrects Stage 1, where I filed them under "not usable". It creates a real decision (§5, D1).
4. **The EU AI Act high-risk dates moved, and it's now law.** Regulation (EU) 2026/1744 (Digital Omnibus on AI), published in the Official Journal on 24 Jul 2026 and in force on 27 Jul 2026 ✅. Details in §3.
5. **Kùzu (embedded graph DB) is archived** (Oct 2025, acquired by Apple) 🟡. Its absence strengthens the DynamoDB + NetworkX choice.

---

## 1. AWS account: Free plan facts
| Fact | Status | Source |
|---|---|---|
| $100 credits on sign-up, plus up to $100 more for completing onboarding activities | ✅ | [AWS Billing: Free Tier](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html) |
| Plan ends after 6 months or when credits run out, whichever is first | ✅ | same |
| Only *Always Free* offers are active (no 12-month trials). Usage beyond them draws on credits | ✅ | same |
| No charges until you upgrade | ✅ | same |
| After expiry: 90 days to upgrade, then the account is closed and its content deleted | 🟡 | [AWS Free Tier Terms](https://aws.amazon.com/free/terms) (via search summary) |
| **Multi-Region / cross-Region features are not supported** | ✅ | [Supported services (new sign-up)](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html) |
| AWS Organizations is not supported (joining one converts the account to Paid) | ✅ | same |
| Paid-plan-only services include **Neptune**, Kinesis, Redshift, EMR, Textract, Translate | ✅ | same |

**Implications:** use one region. Never join an Organization. Neptune is ruled out on two counts (cost and the plan).

## 2. Service-by-service verdict
| Service | Use in project | Free allowance | Verdict |
|---|---|---|---|
| **Lambda** | crawler, API, 3 apps, mocks | 1M requests + 400k GB-s per month, Always Free ✅ ([Free Tier guide](https://docs.aws.amazon.com/whitepapers/latest/how-aws-pricing-works/get-started-with-the-aws-free-tier.html)) | ✅ GO. ~~Cap with reserved concurrency (1–2) as an abuse brake.~~ **[Updated in Stage 4: the account limit is 10, so reserved concurrency can't be set.]** |
| Lambda Function URLs | HTTPS endpoints without API Gateway | ❓ Not listed separately; it's a Lambda feature with no separate price as far as we know | ✅ GO, use `AWS_IAM` auth (not `NONE`). **[Stage 4: pricing to be confirmed on the Function URL docs before M8.]** |
| **DynamoDB** | knowledge graph and evidence store | 25 GB + 25 WCU + 25 RCU, **provisioned mode + Standard table class only**. On-demand reads/writes are *not* free ✅ ([pricing](https://aws.amazon.com/dynamodb/pricing/)) | ✅ GO, provisioned, auto-scaling OFF, Standard class, 1 table (+≤2 GSIs, sharing the 25-unit budget) |
| **CloudWatch Logs** | Lambda logs | 5 GB/month shared across ingestion, storage and Insights queries 🟡 | ⚠️ GO with guardrails: 3-day log retention, log level INFO/WARN, no payload logging |
| EventBridge Scheduler | daily crawl | 14M invocations/month ✅ ([pricing](https://aws.amazon.com/eventbridge/pricing/)) | ✅ GO |
| Resource Explorer | discovery | No charge; only features that rely on AWS Config cost money ✅ ([pricing](https://aws.amazon.com/resourceexplorer/pricing/)) | ✅ GO, but **don't** enable the Config-backed views |
| Resource Groups Tagging API, IAM, Lambda List/Get | discovery | free control-plane APIs | ✅ GO |
| CloudTrail Event history (`LookupEvents`) | evidence of actual use | 90 days of management events, no charge. One region per query; **data events are not included** ✅ ([docs](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html)) | ✅ GO. **Don't** create a trail or CloudTrail Lake. |
| SSM Parameter Store (standard) | config / mock API keys | ❓ Systems Manager is listed as included; standard parameters have historically been free | ✅ GO (prefer it over Secrets Manager) |
| AWS Budgets | cost alarm | Budgets without actions are free ✅ ([FAQ](https://aws.amazon.com/aws-cost-management/aws-budgets/faqs/)) | ✅ GO, set up on day 1 |
| Cognito | auth | 10k MAU Lite/Essentials, doesn't expire 🟡 ([pricing](https://aws.amazon.com/cognito/pricing/)) | ⏸ NOT NEEDED for the MVP (private backend, see §4) |
| S3 | evidence files, IaC artefacts | **No Always Free storage for new accounts. It's credits only** ✅ ([pricing](https://aws.amazon.com/s3/pricing/)) | ⚠️ AVOID by design (see §4) |
| CloudFront | hosting | Always Free 1 TB + 10M requests ✅ ([pricing](https://aws.amazon.com/cloudfront/pricing/pay-as-you-go/)) | ⏸ Not needed (GH Pages chosen) |
| Bedrock / SageMaker | real inference | Available on the Free plan, **paid from credits** ✅ | ❓ Decision D1 |
| Neptune, AWS Config, NAT GW, VPC Flow Logs, Secrets Manager | — | paid or Paid-plan only | ❌ NO-GO |

## 3. Regulatory and standards facts
**EU AI Act after Regulation (EU) 2026/1744.** Verified directly in the [Official Journal text](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202601744) ✅:
| Obligation | Date |
|---|---|
| Prohibitions (Art. 5) + AI literacy (Art. 4) | 2 Feb 2025 (unchanged) |
| **New** Art. 5(1)(ba)/(bb) prohibitions (non-consensual intimate deepfakes, etc.) | 2 Dec 2026 |
| Art. 50(2) synthetic-content marking for generative systems placed on the market before 2 Aug 2026 | 2 Dec 2026 |
| High-risk rules, **Annex III** systems (Art. 6(2)) | **2 Dec 2027** (was 2 Aug 2026), a fixed date |
| High-risk rules, **Annex I** product systems (Art. 6(1)) | **2 Aug 2028** (was 2 Aug 2027) |
| Amending regulation in force | 27 Jul 2026 |

Other changes worth modelling:
- **Art. 4 (AI literacy) was rewritten.** Providers and deployers must "take measures to support" AI literacy. It's a softer, effort-based duty and does not require "any specific level" of literacy.
- **Art. 6(3) registration was simplified.** Systems a provider self-assesses as *not* high-risk must still be registered (Art. 49(2)), but with streamlined Annex VIII content.

**Product consequence:** our use cases' obligations are *date-aware*. In Nov 2026 the Annex III chatbot or ML system has no high-risk obligations in force yet, but AI literacy and Art. 50 transparency already apply. The regulatory timeline view is now a genuinely useful feature.

**Other frameworks:**
- NIST AI RMF **1.0 is still current**. NIST's page says a revision is in progress 🟡 ([NIST](https://www.nist.gov/itl/ai-risk-management-framework)). The Generative AI Profile **NIST AI 600-1** (Jul 2024) is worth including as a sub-profile 🟡.
- NIST publishes an AI RMF ↔ ISO 42001 crosswalk, but it was drafted against the *FDIS* version and NIST says it isn't an endorsement 🟡. Useful as a cross-check, not as a source of truth.
- **STRM (NIST IR 8477).** The five relationship types are equal, subset of, superset of, intersects with, and no relationship. Each mapping gets a strength rating and a rationale type (syntactic, semantic, functional) 🟡, via the [SCF summary](https://securecontrolsframework.com/start-here/set-theory-relationship-mapping-strm). ❓ Re-check against csrc.nist.gov before we build the crosswalk schema.
- **CycloneDX:** v1.6 added most of the current ML-BOM capability and is standardised as ECMA-424 🟡. A v1.7 may exist ❓.
- **Competitors:** Vanta and Drata both support ISO 42001. Neither appears to list the EU AI Act as a fully named framework; both publish guidance only 🟡. Our differentiators (role-aware, date-aware EU AI Act applicability; STRM crosswalk; assurance levels) still hold.
- ISO 27001:2022 Amendment 1:2024 (climate-related wording) ❓ to confirm when we seed controls.

## 4. Architecture adjustments driven by this research
1. **No S3 at all.** The live stack doesn't need it:
   - Evidence goes into DynamoDB items (≤400 KB each), with a SHA-256 hash and provenance fields.
   - Deploy Lambda code by direct zip upload. Terraform/OpenTofu does this natively; AWS SAM and CDK both *require* an S3 artefact bucket.
2. **Keep Lambda packages tiny.** scikit-learn plus numpy exceeds what's practical in a Lambda zip. Train the ML model locally, export its parameters to JSON, and run inference in pure Python. It's still a real trained model, with no heavy runtime.
3. **One frontend data path.** The dashboard reads a **graph snapshot JSON**, both locally and on GitHub Pages. The private backend (Function URLs with IAM auth) handles crawling and writes, then exports the snapshot. No public AWS endpoint, so no Cognito needed for the MVP.
4. **Region:** a single EU region (recommend `eu-west-1`, Ireland). It fits the EU-exposure story and gives us a clean data-residency attribute. Verify Lambda and DynamoDB are offered there (they are in all commercial regions).
5. **Guardrails on day 1:** a $0.01 cost budget with email alert, Free Tier usage alerts, 3-day log retention (reserved concurrency dropped in Stage 4), and a Claude Code hook that pauses before any mutating `aws`/`terraform apply` command.

## 5. Decisions needed
- **D1 — Real Bedrock calls from credits?** On the Free plan, a handful of calls to a small model would cost cents of credit and $0 out of pocket. It's *more* authentic (and gives CloudTrail evidence of actual use), but it bends your "no paid inference" rule. My recommendation: mock by default, with an optional `REAL_BEDROCK=false` adapter switch you flip deliberately for one recorded demo.
- **D2 — IaC tool:** Terraform/OpenTofu (no S3 needed, highly transferable skill) vs AWS SAM (AWS-native, simpler Lambda dev loop, but needs an S3 artefact bucket on credits). My recommendation: Terraform.
- **D3 — Region:** `eu-west-1` (recommended) vs `us-east-1`.

**Decided 2026-11-05:** D1 = **Mock only** (Bedrock is never invoked) · D2 = **Terraform/OpenTofu** · D3 = **eu-west-1**.

## 6. Feasibility verdict
**GO.** Every MVP component has a zero-cost path on your Free plan. Three things can't be done at zero cost and will be simulated, clearly labelled:
- real third-party (OpenAI) calls
- network-level detection of outbound AI API calls
- AWS-Config-based configuration history (we diff crawl snapshots instead)
