# Verity content

Governance content as code ([ADR 0008](../docs/adr/0008-governance-as-code.md)). `uv run verity lint` checks it, and `uv run verity seed` does a dry run. Writing to the real table needs `--target dynamodb` and the owner's approval.

The organisation, people and companies under `org/` are fictional. The mappings are our interpretation, not legal advice and not an official crosswalk.

| Path | Holds |
|---|---|
| `frameworks/` | Requirements of the four instruments |
| `controls.yaml` | The Verity Control Library, the hub |
| `mappings/` | Requirement to control, with an STRM type |
| `rules/obligation_dates.yaml` | When EU AI Act obligations apply |
| `org/` | Kestrel Cloud Ltd and its AI estate |

## A curated subset

The EU AI Act requirements are a curated subset, chosen to cover the three demo use cases. These are left out on purpose: Art. 17, 43, 49, 72 and 73, Art. 26(1), (5) and (6), and Art. 50(3) and (4). A requirement missing here is not a statement that it does not apply.

## Reading a mapping

The requirement is concept A and the control is concept B ([ADR 0017](../docs/adr/0017-m4-content-semantics.md)).

| `strm` | Meaning here |
|---|---|
| `equal` | Same content. None are claimed, because the hub is in our own words |
| `subset_of` | The control covers the whole requirement and more |
| `superset_of` | The control covers only part of the requirement |
| `intersects_with` | Each has content the other lacks |
| `no_relationship` | The content does not overlap, even if the names sound alike |

`sufficiency: full` means the control belongs to a set that together covers the requirement.

## Strength rubric

NIST IR 8477 defines no strength rating. This 1 to 10 scale is a Verity convention, taken from the Secure Controls Framework's practice.

| Strength | Meaning |
|---|---|
| 9 to 10 | Practically the same. Needed for `equal` |
| 7 to 8 | Strong: the main point of both is the same, and the differences are minor |
| 5 to 6 | Moderate: a real overlap, with something material on one side missing from the other |
| 3 to 4 | Weak: one is a narrow part of the other, or they share a theme with different aims |
| 1 to 2 | Marginal: related only at a high level |

Mappings from a text nobody read stop at 5 ([ADR 0018](../docs/adr/0018-unread-standards.md)).

## How each source was checked

| Instrument | Checked against | `verified_against` |
|---|---|---|
| EU AI Act | Regulation (EU) 2024/1689 and (EU) 2026/1744 in the Official Journal, read through the EU Publications Office on 2026-11-05 | `primary_text` |
| NIST AI RMF | NIST's AI RMF Core page, read on 2026-11-05 | `primary_text` |
| ISO/IEC 42001 and 27001 | Public listings of IDs and titles only. Nobody here has read the standards, and iso.org refuses automated reads, so its catalogue pages were not checked either | `public_listing` |

**Where listings disagree.** For ISO/IEC 42001, [Modulos](https://docs.modulos.ai/frameworks/iso-42001/annexes-a-d.html) and [RiskProfs](https://riskprofs.com/iso-42001-annex-a-controls-list/) agree on all 38 Annex A IDs and titles, and those are the ones used. [CertPro](https://certpro.com/hub/iso-42001/controls/iso-42001-controls-list/) numbers many controls differently (for example A.6.4 for verification and validation, and A.8.2 for supplier relationships), lists 21 IDs and has no A.10 section. We followed the two that agree. Only someone with the standard can settle it.
