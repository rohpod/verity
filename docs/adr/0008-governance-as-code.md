# 0008 — Human governance decisions as code
- **Status:** Accepted (2026-11-05)

## Context
Some decisions must be made by humans, not inferred by the tool:
- risk-tier confirmations
- attestations
- risk treatments
- L4 verifications

A write API with an editable UI would need authentication, which adds cost and complexity for the MVP.

## Decision
These decisions live as YAML under `content/decisions/` and are reviewed through pull requests. `verity seed` loads them into the graph, with the commit SHA and author recorded as provenance. The dashboard stays read-only.

## Alternatives
A Lambda write API (Function URL with IAM auth) plus forms in the UI. This is deferred to a later milestone.

## Consequences
- Version history, approval trails and diffs come free from git.
- The approving pull request serves as the audit record.
- This is less SaaS-like for non-technical users, which is acceptable for a portfolio project.
- It also mirrors "policy-as-code" practice.
