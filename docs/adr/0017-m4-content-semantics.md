# 0017 — M4 content semantics: mapping direction, strength, dates and provenance
- **Status:** Accepted (2026-11-05). Refines [0004](0004-hub-and-spoke-strm-crosswalk.md), [0010](0010-assessment-and-crosswalk-semantics.md) and [0012](0012-graph-schema-refinements.md); all stay in force.

## Context
M4 is the first milestone that writes real content, so every ambiguity in the mapping model becomes data. Planning it meant re-reading NIST IR 8477 (final, February 2024) in full, which ADR 0004 had only checked through the Secure Controls Framework's summary. Findings:
- The five relationship types and three rationales match `enums.py`. The report says a relationship type and a rationale "must be used together".
- **NIST does not define a strength rating.** The 1 to 10 scale is the Secure Controls Framework's own practice. ADR 0004 and architecture §F present it as part of STRM.
- "Concept A is a subset of concept B" means B contains everything A does and more. Our documents never say which side of a mapping is A, so `subset_of` could be read either way.
- Our model has one `sufficiency` flag per mapping, but a set of partial overlaps can cover a requirement together, and nothing says when a mapping may be `full`.
- Obligation dates are data, but `Requirement` has one record per article, and one article can have several dates (Annex I and Annex III systems, or Art. 50(2) for systems already on the market).
- iso.org refuses automated reads, the owner has no licensed ISO copies, and public listings of ISO/IEC 42001 sub-control IDs disagree with each other.
- The EU AI Act application dates were confirmed in this session only by secondary commentary, because EUR-Lex returned an empty page to automated fetches. Stage 2 read them from the Official Journal text.

## Decision
**Mapping semantics**
- **Direction.** In `MAPS_TO`, concept A is the requirement and concept B is the control. `subset_of` means the control covers everything the requirement asks for and more. `superset_of` means the control covers only part of it.
- **Strength is a Verity convention.** It stays 1 to 10, taken from the Secure Controls Framework and not from NIST, with a written rubric in the content. `equal` needs a strength of at least 9.
- **Rationale type.** Only `semantic` and `functional` are accepted. `syntactic` compares wording, and the hub is written in our own words, so there is no wording to compare. A requirement and a control have one mapping, because edge identity has no rationale qualifier.
- **When a mapping is `full`.** `equal` and `subset_of` must be `full`. `superset_of` and `intersects_with` may be `full` only if the requirement has at least two `full` mappings, because one control that covers only part of a requirement cannot satisfy it alone.

**Dates**
- **Obligation dates live in `content/rules/obligation_dates.yaml`**, not on `Requirement`. Each row has `id`, `date`, `covers`, `source_url` and `last_verified`. M5 reads them into `APPLIES_TO.in_force_from`. No date appears in a requirement summary.
- **No EU AI Act date enters the file before the Official Journal text has been read.** The owner reads it in a browser, or approves Claude in Chrome for it.

**Provenance and verification**
- **`Requirement.verified_against`** is a required field with values `primary_text` and `public_listing`. Every ISO entry is `public_listing`, so the demo never implies a check against the standard.
- **An ISO ID needs two independent public sources that agree.** An ID with fewer is dropped, even if ISO coverage falls below the 8 to 12 entries planned per instrument.
- **`source` on seeded records.** Frameworks, requirements, controls and mappings are `seeded`. The Kestrel organisation, people and synthetic systems are `synthetic`. The three demo systems are `declared`. Mock providers and their models are `simulated`.

**System facts**
- **`AISystem` gains the facts M5's rules read**: `roles`, `use_domains`, `interacts_with_people`, `generates_synthetic_content` and `first_placed_on_market`. Each defaults to unknown. They are facts only. A risk tier is an output of M5 and a human decision (ADR 0008), so it is not a field.

## Alternatives
| Option | Why not chosen |
|---|---|
| Keep strength as a NIST feature | It is not in IR 8477, and the demo would claim a standard it does not follow |
| Drop strength and use the STRM type alone | The crosswalk takes the weaker of two strengths (ADR 0010), and the type alone cannot rank two `subset_of` mappings |
| Let any `sufficiency: full` stand | A single partial-overlap control could then satisfy a requirement, which is the false assurance STRM exists to prevent |
| Store dates on `Requirement` | One article has several dates, so a single field would hide the conditions |
| Fill ISO gaps from one public listing | Listings disagree, so a wrong ID would look verified |

## Consequences
- Existing fixtures in `tests/graph/estate.py` map with `subset_of`, `superset_of` and `intersects_with`. They are updated alongside the new fields and the lint rules.
- Mappings are our interpretation. The lint checks form (rationale length, the sufficiency rules, coverage), not judgement, so the owner reads the mappings in the content PR.
- ISO coverage may be thinner than the other instruments. That is accepted over an unverified ID.
- Re-seeding does not remove anything, so a mapping deleted from YAML stays open in the graph. M8 decides on pruning before the first live re-seed.
