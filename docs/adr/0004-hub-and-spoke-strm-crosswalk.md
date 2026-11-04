# 0004 — Hub-and-spoke crosswalk using NIST IR 8477 STRM
- **Status:** Accepted (2026-11-05)

## Context
We map four instruments: ISO/IEC 42001, ISO/IEC 27001, the EU AI Act and the NIST AI RMF. Requirements that sound similar are often not equivalent, and treating them as equal is a major source of false assurance. NIST IR 8477 defines Set Theory Relationship Mapping (STRM) for this problem:
- relationship types: equal, subset of, superset of, intersects with, no relationship
- a strength rating for each mapping
- a rationale type: syntactic, semantic or functional

## Decision
- Build an internal **Verity Control Library** (the hub), written in our own words.
- Map each framework requirement to hub controls (the spokes). Each mapping records the STRM type, strength (1–10), rationale type, written rationale and a `sufficiency` flag (full or partial).
- **Derive** cross-framework links by composing two spokes:
  - each derived link is labelled "via VC-xxx"
  - its strength is the weaker of the two spokes
  - it is never presented as `equal`
- A requirement is shown as *Satisfied* only when its full-sufficiency control set is implemented at assurance L2 or higher. Otherwise it is *Partially addressed*.

## Alternatives
Pairwise framework-to-framework mapping. This needs N² mapping sets (6 for 4 frameworks) and errors compound as they are chained. It is rejected.

## Consequences
- Adding a framework costs one new spoke.
- Mappings are our interpretation, so the UI shows the rationale and the "derived" labels.
- ISO entries store IDs plus original summaries only. **❓** The STRM definitions were verified through the Secure Controls Framework's summary; we will re-check them against csrc.nist.gov before seeding content.
