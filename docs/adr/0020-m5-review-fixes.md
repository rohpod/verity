# 0020 — M5 review fixes: decision lifecycle, expiry, unknown facts and severity
- **Status:** Accepted (2026-11-06). Refines [0017](0017-m4-content-semantics.md) and [0019](0019-m5-rules-and-assessment.md); both stay in force, except where *Decision* 1 and 4 narrow 0019.

## Context
The end-of-milestone review of M5 passed the validation criteria but reproduced cases where the engine shows less risk or more assurance than it should:
- **A correction or deletion may not take effect.** Editing a decision creates new Evidence and the old node stays. If `decided_on` is unchanged, the two tie and the Evidence ID hash picks the winner: the old decision won 10 of 60 times for a verification and 37 of 40 for a risk tier. Deleting a file does nothing, so an L4 sign-off cannot be revoked. A fresh in-memory seed hides this, so it would first appear on the real table.
- **Risk-tier decisions ignore time.** An expired `not_high_risk` decision still removed every Chapter III edge, with no finding, which breaks D3. A decision also applied at an `as_of` before it was made.
- **Unknown facts fail open.** A system with no `roles` or `use_domains` got no obligations and no finding, and lint passed. ADR 0017 calls these facts unknown, and ADR 0019 chooses the cautious reading. M6 makes this likely, because discovered systems may arrive without them.
- **Severity carries no signal.** 427 of 438 findings were high `no_evidence`. Only 22 of the 430 `no_evidence` findings back an in-scope EU AI Act duty. The rest back ISO and NIST requirements that Kestrel adopted by choice.
- **Assessments outlive their scope.** When a system leaves scope, its `APPLIES_TO` edges close, but assessments of controls it no longer reaches stay stored and would reach the M9 snapshot.

The review also read Art. 111(2) as amended, in the Official Journal text through the EU Publications Office. It confirmed ADR 0019's reading and found two parts we do not model (*Decision* 7).

These fixes make no AWS changes.

## Decision
1. **A decision is immutable once seeded.** A change is a new decision that names the old one in `supersedes`, a list of decision IDs on every decision. This replaces ADR 0019's consequence that an edit creates a new Evidence node beside the old one. `verity seed` refuses if a stored decision is missing from the content (`decision_removed`) or has a different `file_sha256` (`decision_edited`), and the message says to add a superseding decision or a revocation.
2. **Revocation is a decision kind.** `kind: revocation` has a required `subject` and a non-empty `supersedes`. It is Attestation evidence with an `ABOUT` edge, and it has no `control` or `scope`, so it can never count as an assessment.
3. **Supersession is time-aware and permanent.** A decision is superseded at `as_of` if a decision collected by `as_of` names it. The superseding decision's own expiry does not bring the old one back. Lint refuses a target that does not exist, one with a different subject, one decided later than the decision naming it, and two unsuperseded decisions with the same kind, subject, control and `decided_on`. So the Evidence ID never decides a result.
4. **A risk-tier decision counts only while in force.** It must be unsuperseded, collected by `as_of` and not past `valid_until`, and the latest such decision wins. `applicable_edges` takes `as_of`. **This narrows ADR 0019, decision 5:** which `APPLIES_TO` edges exist now depends on `as_of`, through the decisions in force. The function stays pure (D5). If only expired decisions remain:

   | Expired decision | Annex III domain? | Tier | Finding |
   |---|---|---|---|
   | Either tier | Yes | Candidate | `risk_tier_expired`, high |
   | `high_risk` | No | Candidate | `risk_tier_expired`, high |
   | `not_high_risk` | No | Not high-risk | `risk_tier_expired`, medium |

   `risk_tier_unconfirmed` is not raised as well. A system whose decisions were all superseded with nothing in force goes back to its facts.
5. **Empty `roles` and `use_domains` mean unknown.** Each raises `unknown_fact` at high severity, because no obligation can be derived without them. `use_domains` is exempt while a risk-tier decision is in force. No rule applies on an unknown fact: the finding asks a person to record it.
6. **`no_evidence` severity follows binding law.** `Framework` gains a required `binding: bool`, true for `euaia` and false for the adopted frameworks. The finding is high only if the control backs an in-force or conditional requirement of a binding framework, otherwise medium. *Conditional* stays in scope, because it holds the Talent Screening bias-test gap, and ADR 0019 keeps those duties visible on purpose.
7. **Two parts of Art. 111(2) stay unmodelled.** The article also covers a system "put into service" before the date, and requires providers and deployers of systems intended for public authorities to comply by 2 August 2030. `first_placed_on_market` stands in for both events, and no Kestrel system is intended for a public authority. Revisit if either changes.
8. **An assessment no longer produced is ended.** `verity assess` sets `valid_to` on an open ControlAssessment in scope that this run did not produce, which closes its edges. A later run that produces it reopens it. With `--system`, only assessments scoped to that system are touched. Stored history is kept.

## Alternatives
| Option | Why not chosen |
|---|---|
| Delete the old Evidence when a decision file changes | Evidence is immutable (§G), and the audit trail is the point of keeping decisions as code |
| Let the latest `decided_on` win and require a new date on edits | A deleted file still stays in force, and a same-day correction is a real case |
| Order same-day decisions by a revision number | Handles an edit but not a revocation, and needs a second mechanism for it |
| Keep `APPLIES_TO` independent of `as_of` and filter on read | Every reader would have to repeat the tier logic, and stored edges would still show duties a decision removed |
| Keep an expired `not_high_risk` decision until someone renews it | The system would quietly stay out of scope, which is the failure the review found |
| Apply high-risk rules to a system with unknown `use_domains` | Would give every newly discovered system Chapter III duties, and the finding asks the same question |
| Raise `no_evidence` severity by provider scope as well | Rests on where a control sits and not on whether law requires it |
| Name binding frameworks in the rules file | Bindingness is a fact about the instrument, so it belongs on `Framework` |
| Mark a dropped assessment *Not applicable* | That state means the engine resolved the control, which it did not |

## Consequences
- A typo fix in a seeded decision needs a superseding decision. That is stricter than a normal edit, and it is the price of a decision being a signed record.
- `verity seed` reads every Evidence node first. It stays free, but M6 expects tens of thousands of Evidence items, so M8 checks how long this takes.
- A risk-tier decision's expiry changes stored edges on the next assessment after `valid_until`, so "a second run writes nothing" holds only for the same decisions in force.
- About 22 `no_evidence` findings stay high on the real content. The mock OpenAI DPA gap (VC-050) becomes medium, because VC-050 maps only to ISO and NIST. A DPA duty from data protection law is outside the content, and that is not a statement that it is unimportant.
- A new framework file must state `binding`.
- Pruning deleted *mappings* stays open for M8. This ADR covers decisions only.
