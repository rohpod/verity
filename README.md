# Verity

**AI governance, risk and compliance: discover the AI you run, map it to obligations, and prove it with evidence.**

Verity is an open-source portfolio project exploring what an *AI-specific* GRC platform built around AI systems. For a single AWS account it:

- **discovers** AI workloads, scores how confident it is that each is AI, and explains why;
- maintains an **AI system registry** (owners, purpose, models, providers, data, risk tier);
- maps systems to **ISO/IEC 42001, ISO/IEC 27001, the EU AI Act and the NIST AI RMF** through a typed crosswalk (NIST IR 8477 set-theory relationships), backed by a **knowledge graph**;
- separates *mapped*, *implemented*, *evidenced*, *tested* and *verified*, so a single configuration check never turns an obligation green.

> **Status:** Stage 3 (architecture). No application code yet. See [`docs/`](docs/).

## Real vs simulated

Verity is built under a strict **zero-cost, AWS-only** constraint, so some things are simulated. The UI labels every record.

| Component | Status |
|---|---|
| AWS resources (Lambda, DynamoDB, IAM, Scheduler) | **Real**, deployed via Terraform in one AWS account |
| Discovery crawler | **Real**, read-only AWS APIs |
| Talent-screening ML model | **Real**, trained locally on **synthetic** data |
| Bedrock inference (support assistant) | **Simulated**: a mock with a Converse-API shape. Bedrock is never invoked |
| OpenAI API (contract insights) | **Simulated**: an OpenAI-compatible mock endpoint |
| Company "Kestrel Cloud Ltd", its people and ~25 extra AI systems | **Fictional / synthetic** |
| Public demo | **Static snapshot** of the real graph, account IDs redacted |

## Documentation
- [Stage 1: Product discovery](docs/stage-1-discovery.md)
- [Stage 2: Feasibility & zero-cost verification](docs/stage-2-feasibility.md)
- [Architecture](docs/architecture.md)
- [Architecture Decision Records](docs/adr/)

## Disclaimer
Verity is a learning project, not legal advice. Framework mappings are the author's own interpretation. ISO standards are referenced by clause ID with original summaries only; no ISO text is reproduced.
