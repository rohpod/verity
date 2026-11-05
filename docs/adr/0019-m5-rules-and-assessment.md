# 0019 — M5 rules and assessment: guardrail, Art. 111(2), candidates and decisions
- **Status:** Accepted (2026-11-05). Refines [0005](0005-control-assessment-assurance-ladder.md), [0008](0008-governance-as-code.md), [0010](0010-assessment-and-crosswalk-semantics.md) and [0017](0017-m4-content-semantics.md); all stay in force, except where *Decision* 4 narrows 0008.

## Context
M4 put the governance content in place, but nothing yet says what applies to whom, or whether it is met. M5 adds that. Reviewing M4 for it found two problems:
- **Three obligations can go green on one automated check.** Art. 12, 50(1) and 50(2) map only to controls that are all automatable. Once a check passes at L3, each requirement would show *Satisfied* with no person involved. That breaks the guardrail in architecture §G.
- **Art. 111(2) changes the Talent Screening story.** Regulation (EU) 2026/1744 Art. 111(2) puts a high-risk system placed on the market before Chapter III applies in scope only after a significant change in its design. Talent Screening's `first_placed_on_market` is 2026-06-15, before the Annex III date of 2027-12-02. A date alone would overstate its obligations. The owner decided that it keeps its 2026 launch and its Chapter III duties show as *Conditional*.

Further gaps surfaced while planning: a parent such as Art. 9 holds only selected sub-clauses, "unmapped" mixes two cases, a high-risk finding needs a person's decision, and a requirement whose mapped controls are all unmet had no status.

M5 makes no AWS changes. Everything runs on `InMemoryRepository` and moto.

## Decision
1. **Automated-only guardrail.** A requirement is *Satisfied* only if at least one control in its full set is non-automatable, or at least one is at L4. Otherwise it stops at *Partially addressed*, with reason `automated_only`. This covers Art. 12, 50(1) and 50(2) with no content change. It is an engine rule and not a lint rule, so lint still passes.
2. **Art. 111(2).** A new `AppliesCondition.LEGACY_SIGNIFICANT_CHANGE` on `AppliesToEdge`, and a new `AISystem.significant_change_on: date | None`. It applies only to the Chapter III rules. It is not extended to Art. 4 or Art. 50, although the article says "this Regulation", because no system in the estate needs that reading.
3. **High-risk is a candidate until a person decides.** Facts make a candidate. A `risk_tier` decision confirms or rejects it (ADR 0008). Rules apply to unconfirmed candidates, which is the cautious choice, and raise a `risk_tier_unconfirmed` finding.
4. **Decisions become Evidence with inline content.** `verity seed` loads them. `Evidence.content_ref` must sit under `evidence/`, so a decision records its file path and sha256 in inline content. **This narrows ADR 0008:** the commit SHA is looked up at export (M9, D10) and not at seed, because a SHA inside hashed content would create a new Evidence node on every commit.
5. **Stored versus derived.** `verity assess` stores `APPLIES_TO` edges and ControlAssessments. Applicability status, freshness, requirement status and findings are derived on read from `as_of` and never stored (D5).
6. **Parents** (Art. 9, 10, 26) are never *Satisfied* from their children, because the content holds only selected sub-clauses. The rollup is *Partially addressed* if any child is, else *Not met*.
7. **Not addressed** covers both "never mapped" and "reviewed, `no_relationship`", with a `reason` of `never_mapped` or `reviewed_no_control`.
8. **New state: *Not met*.** A requirement with usable mappings where none is met. Architecture §F had no word for it.
9. **Art. 4a** stays out of the control library, because Kestrel records no special-category processing. The note moves to M11.
10. **Risk treatment decisions** (named in ADR 0008) are deferred. Nothing in M5 reads them.

The rule tables themselves (applicability, control assessment, requirement status, findings) are the approved M5 plan. The owner reads `content/rules/applicability.yaml` when it lands in PR 3, because the rules are our interpretation of the law and not legal advice.

## Alternatives
| Option | Why not chosen |
|---|---|
| Require an L4 sign-off in the content for Art. 12, 50(1) and 50(2) | Needs new non-automatable controls, which would be invented only to satisfy the engine |
| Make the guardrail a lint rule | Mappings would be correct while the result stayed wrong, and a later content change could reopen the hole silently |
| Show Talent Screening as in force from 2 Dec 2027 | Overstates its duties, which Art. 111(2) says do not apply without a significant change |
| Hide Talent Screening's Chapter III duties until a change | Hides a risk the owner should see. *Conditional* shows it and says why |
| Apply Art. 111(2) to Art. 4 and Art. 50 | The article says "this Regulation", but no system in the estate needs that reading, so the rule would be untested |
| Treat unconfirmed high-risk candidates as not high-risk | The cautious reading is the safe one, and a finding asks a person to decide |
| Let a parent be *Satisfied* when its children are | The content holds selected sub-clauses only, so the parent would claim more than was mapped |
| Store the commit SHA in decision evidence | It sits inside hashed content, so every commit would create a new Evidence node |

## Consequences
- ISO requirements still never show as *Satisfied* (ADR 0018), and now Art. 12, 50(1) and 50(2) cannot either without a human control or an L4 decision.
- Talent Screening shows *Conditional* Chapter III edges, and the status turns to in force only when `significant_change_on` is recorded on or after 2027-12-02.
- Until the owner decides `candidate-cv-parser`, its rules apply and a high finding stays open. That is intended.
- Decisions are loaded as Evidence, so a decision edit creates a new Evidence node and the old one stays.
- Estimated write counts for a live assessment are measured in M5 and recorded for M8.
