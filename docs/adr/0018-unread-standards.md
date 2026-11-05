# 0018 — Mappings from a standard nobody read claim only an overlap
- **Status:** Accepted (2026-11-05). Refines [0017](0017-m4-content-semantics.md), which stays in force.

## Context
ADR 0017 marks ISO entries `public_listing`, so the demo never implies a check against the standard. Writing the mappings exposed a further problem. STRM compares the content of two concepts, and for ISO we hold a control's ID and short title only. `subset_of` with `sufficiency: full` would state that a hub control covers everything an ISO control asks for, which cannot be known without reading it. A *Satisfied* ISO requirement would then rest on text nobody here has seen. `no_relationship` makes the same kind of claim in the other direction.

Public listings also do not fully agree. Two listings agree on all 38 ISO/IEC 42001 Annex A IDs, and a third numbers many controls differently. Agreement between two sites is evidence of an ID, not proof, and we cannot show that the two sites are independent of each other.

## Decision
- **A mapping from a `public_listing` requirement must be `intersects_with`, `partial`, with a strength of 5 or less.** The linter enforces it (`unread_mapping_overclaims`).
- **So an ISO requirement can never show as *Satisfied*.** Its full set is empty, so the best it can show is *Partially addressed* (D2). This is the intended result.
- **Each ISO rationale says it comes from the public title only.**
- **The rule follows the field, not the framework.** If the owner buys the standards and reads them, an entry moves to `primary_text` and the limit stops applying to it, one entry at a time.
- **The two-listing rule stays, with the dissenting listing recorded** in `content/README.md`.

## Alternatives
| Option | Why not chosen |
|---|---|
| Map ISO entries the same way as the others | The demo would claim set relationships nobody checked, and could show an ISO requirement as Satisfied, which is the false assurance this project exists to prevent |
| Leave ISO unmapped until the standards are bought | Loses the crosswalk to two of the four instruments, although an honest overlap is still useful |
| Use `no_relationship` where a title looks unrelated | It is as much a claim about the text as `subset_of` |
| Rely on another party's published mapping | Those are third-party interpretations of text we still could not check |

## Consequences
- ISO requirements never go green in the demo, and the UI needs to say why. M10 shows the `verified_against` value beside them.
- Derived links through an ISO spoke have a strength of 5 or less, because a derived link takes the weaker spoke (ADR 0010).
- An ID could still be wrong if both listings share one mistake. `public_listing` tells the reader that risk exists.
