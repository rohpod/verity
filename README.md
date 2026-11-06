# Verity

**AI governance, risk and compliance: discover the AI you run, map it to obligations, and prove it with evidence.**

Verity is an open-source portfolio project exploring what an *AI-specific* GRC platform could look like. For a single AWS account it:

- **discovers** AI workloads, scores how confident it is that each is AI, and explains why;
- maintains an **AI system registry** (owners, purpose, models, providers, data, risk tier);
- maps systems to **ISO/IEC 42001, ISO/IEC 27001, the EU AI Act and the NIST AI RMF** through a typed crosswalk (NIST IR 8477 set-theory relationships), backed by a **knowledge graph**;
- separates *mapped*, *implemented*, *evidenced*, *tested* and *verified*, so a single configuration check never turns an obligation green.

> **Status:** Stage 4. The local graph core (M1), its DynamoDB repository (M2), the AWS account baseline (M3: the `verity-graph` table and a cost budget, tested live) the governance content with `verity seed` (M4, not yet seeded to AWS) the rules with `verity assess` and `verity attest` (M5, run locally) and the discovery pipeline with `verity crawl --local` (M6, tested on `moto` and a recorded fixture; nothing reads AWS yet) are built. The demo estate code (M7: two mocks, the `verity_ai` adapters, five apps, a local talent model and deterministic zips) is written and tested with `moto` and fakes. No Lambda or crawler is deployed yet and nothing reads AWS, so those "Real" rows below describe the plan. See [`docs/stage-4-milestones.md`](docs/stage-4-milestones.md).

## Real vs simulated

Verity is built under a strict **zero-cost, AWS-only** constraint, so some things are simulated. The UI labels every record.

| Component | Status |
|---|---|
| AWS resources (Lambda, DynamoDB, IAM, Scheduler) | **Real**, deployed via Terraform in one AWS account |
| Discovery crawler | **Real**, read-only AWS APIs |
| Talent-screening ML model | **Real**, trained locally on **synthetic** data, with pure-Python inference |
| Bedrock inference (support assistant) | **Simulated**: `mock-bedrock` has a Converse-API shape and labels itself. Bedrock is never invoked, and a test fails if a real client appears |
| OpenAI API (contract insights, shadow summariser) | **Simulated**: `mock-openai` is an OpenAI-shaped Function URL that labels itself. The adapters refuse any other endpoint |
| Usage records | Labelled **simulated**: they record calls to the mocks, and only for third-party models |
| Company "Kestrel Cloud Ltd", its people and ~25 extra AI systems | **Fictional / synthetic** |
| Public demo | **Static snapshot** of the real graph, account IDs redacted |

## Documentation
- [Stage 1: Product discovery](docs/stage-1-discovery.md)
- [Stage 2: Feasibility & zero-cost verification](docs/stage-2-feasibility.md)
- [Architecture](docs/architecture.md)
- [Stage 4: Milestone plan](docs/stage-4-milestones.md)
- [Why M3, M8 and M9 are open](docs/open-milestones.md)
- [M10 and M11 plan](docs/m10-m11-plan.md)
- [Architecture Decision Records](docs/adr/)

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch, commit and pull request standards.

## License
[MIT](LICENSE) © 2026 Rohan Poddar. The license covers this project's own code and documentation, not the third-party standards and regulations it references.

## Disclaimer
Verity is a learning project, not legal advice. Framework mappings are the author's own interpretation. ISO standards are referenced by clause ID with original summaries only; no ISO text is reproduced.
