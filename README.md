# Verity

**AI governance, risk and compliance: discover the AI you run, map it to obligations, and prove it with evidence.**

Verity is an open-source portfolio project exploring what an *AI-specific* GRC platform could look like. For a single AWS account it:

- **discovers** AI workloads, scores how confident it is that each is AI, and explains why;
- maintains an **AI system registry** (owners, purpose, models, providers, data, risk tier);
- maps systems to **ISO/IEC 42001, ISO/IEC 27001, the EU AI Act and the NIST AI RMF** through a typed crosswalk (NIST IR 8477 set-theory relationships), backed by a **knowledge graph**;
- separates *mapped*, *implemented*, *evidenced*, *tested* and *verified*, so a single configuration check never turns an obligation green.

> **Status:** Stage 4, with M0 to M10 done and M11 (the stage close) in review. The graph core and its DynamoDB repository (M1, M2), the account baseline (M3), the governance content and `verity seed` (M4), the rules with `verity assess` and `verity attest` (M5), the discovery pipeline (M6) and the demo estate (M7) are built. The estate and crawler are deployed to the Free plan account (M8), where a scheduled crawl run finished on 2026-11-07 and credits were reported unchanged ([ADR 0032](docs/adr/0032-m8-scheduled-run.md)). A snapshot of the live graph was exported, scanned and reviewed (M9, [ADR 0033](docs/adr/0033-m9-live-snapshot.md)), and the dashboard (M10) reads only that file and is published at **<https://rohpod.github.io/verity/>**. M11's decisions are in [ADR 0034](docs/adr/0034-m11-close-decisions.md). See [`docs/stage-4-milestones.md`](docs/stage-4-milestones.md).

## Real vs simulated

Verity is built under a strict **zero-cost, AWS-only** constraint, so some things are simulated. The UI labels every record.

| Component | Status |
|---|---|
| AWS resources (Lambda, DynamoDB, IAM, Scheduler) | **Real**, deployed with OpenTofu in one AWS account on the Free plan. The daily crawl schedule is `ENABLED` and configured for 03:00 UTC. One scheduled run has happened, at 07:30 UTC on 2026-11-07 under a temporary cron, and the 03:00 UTC cron has not run yet |
| Discovery crawler | **Real**: read-only AWS APIs, writing only to its own table. It has been invoked by hand against the account, and one scheduled run has finished (2026-11-07) |
| Talent-screening ML model | **Real**, trained locally on **synthetic** data, with pure-Python inference |
| Bedrock inference (support assistant) | **Simulated**: `mock-bedrock` has a Converse-API shape and labels itself. Bedrock is never invoked, and a test fails if a real client appears |
| OpenAI API (contract insights, shadow summariser) | **Simulated**: `mock-openai` is an OpenAI-shaped Function URL that labels itself. The adapters refuse any other endpoint |
| Usage records | Labelled **simulated**: they record calls to the mocks, and only for third-party models |
| Company "Kestrel Cloud Ltd", its people and ~25 extra AI systems | **Fictional / synthetic** |
| Human sign-offs and decisions (L4 attestations, the DPA document, two risk tiers) | **Simulated**: made by fictional people, marked `simulated: true`, and shown as *simulated sign-off* |
| Public demo | **Real data, redacted:** a static snapshot of the live graph (`as_of` 2026-11-07T12:20:39Z, `data_source: live`) is published at <https://rohpod.github.io/verity/> on GitHub Pages, the one place outside AWS. The account ID and Function URLs are redacted, the file passed an independent scan and a review against the real values ([ADR 0033](docs/adr/0033-m9-live-snapshot.md)), and every page lists what in it is not real |

## Documentation
- [Stage 1: Product discovery](docs/stage-1-discovery.md)
- [Stage 2: Feasibility & zero-cost verification](docs/stage-2-feasibility.md)
- [Architecture](docs/architecture.md)
- [Stage 4: Milestone plan](docs/stage-4-milestones.md)
- [Milestone status: M3, M8, M9 and M10](docs/open-milestones.md)
- [M10 and M11 plan](docs/m10-m11-plan.md)
- [Architecture Decision Records](docs/adr/)

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch, commit and pull request standards.

## License
[MIT](LICENSE) © 2026 Rohan Poddar. The license covers this project's own code and documentation, not the third-party standards and regulations it references.

## Disclaimer
Verity is a learning project, not legal advice. Framework mappings are the author's own interpretation. ISO standards are referenced by clause ID with original summaries only; no ISO text is reproduced.
