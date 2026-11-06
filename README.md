# Verity

**AI governance, risk and compliance: discover the AI you run, map it to obligations, and prove it with evidence.**

Verity is an open-source portfolio project exploring what an *AI-specific* GRC platform could look like. For a single AWS account it:

- **discovers** AI workloads, scores how confident it is that each is AI, and explains why;
- maintains an **AI system registry** (owners, purpose, models, providers, data, risk tier);
- maps systems to **ISO/IEC 42001, ISO/IEC 27001, the EU AI Act and the NIST AI RMF** through a typed crosswalk (NIST IR 8477 set-theory relationships), backed by a **knowledge graph**;
- separates *mapped*, *implemented*, *evidenced*, *tested* and *verified*, so a single configuration check never turns an obligation green.

> **Status:** Stage 4. The local graph core (M1), its DynamoDB repository (M2), the AWS account baseline (M3: the `verity-graph` table and a cost budget, tested live) the governance content with `verity seed` (M4, not yet seeded to AWS) the rules with `verity assess` and `verity attest` (M5, run locally) and the discovery pipeline with `verity crawl --local` (M6, tested on `moto` and a recorded fixture; nothing reads AWS yet) are built. The demo estate code (M7: two mocks, the `verity_ai` adapters, five apps, a local talent model and deterministic zips) is written and tested with `moto` and fakes. The estate and crawler are deployed to the Free plan account and the table holds a first live crawl (M8), but M3 and M8 stay open until a scheduled run and a credit read. The snapshot export (M9) is built, tested on `moto` and the recorded fixture, and has not been run on the live table. The dashboard (M10) is built and reads only `snapshot.json`; it is not published, because no live snapshot exists yet, so there is no demo link. See [`docs/stage-4-milestones.md`](docs/stage-4-milestones.md).

## Real vs simulated

Verity is built under a strict **zero-cost, AWS-only** constraint, so some things are simulated. The UI labels every record.

| Component | Status |
|---|---|
| AWS resources (Lambda, DynamoDB, IAM, Scheduler) | **Real**, deployed with OpenTofu in one AWS account on the Free plan. The daily crawl schedule is `DISABLED` and has not run yet |
| Discovery crawler | **Real**: read-only AWS APIs, writing only to its own table. It has been invoked by hand against the account; no scheduled run has happened yet |
| Talent-screening ML model | **Real**, trained locally on **synthetic** data, with pure-Python inference |
| Bedrock inference (support assistant) | **Simulated**: `mock-bedrock` has a Converse-API shape and labels itself. Bedrock is never invoked, and a test fails if a real client appears |
| OpenAI API (contract insights, shadow summariser) | **Simulated**: `mock-openai` is an OpenAI-shaped Function URL that labels itself. The adapters refuse any other endpoint |
| Usage records | Labelled **simulated**: they record calls to the mocks, and only for third-party models |
| Company "Kestrel Cloud Ltd", its people and ~25 extra AI systems | **Fictional / synthetic** |
| Human sign-offs and decisions (L4 attestations, the DPA document, two risk tiers) | **Simulated**: made by fictional people, marked `simulated: true`, and shown as *simulated sign-off* |
| Public demo | **Planned: a static snapshot** of the live graph with the account ID redacted. The export and the dashboard are built and tested on a recorded fixture, but no live snapshot has been exported or reviewed, and nothing is published |

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
