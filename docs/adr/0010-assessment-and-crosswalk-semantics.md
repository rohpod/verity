# 0010 — Assessment and crosswalk semantics
- **Status:** Accepted (2026-11-05). Refines [0004](0004-hub-and-spoke-strm-crosswalk.md) and [0005](0005-control-assessment-assurance-ladder.md); both stay in force.

## Context
Walking the architecture against the Stage 4 milestones exposed gaps that would otherwise surface as bugs.

## Decision
- **Satisfied needs a non-empty full set (D2).** A requirement whose full-sufficiency control set is empty can never be *Satisfied*. A requirement with no mappings is *Not addressed*, a new state.
- **Stale evidence does not count (D3).** Only non-stale evidence contributes to a control's effective assurance level.
- **Evidence IDs (D4).** The ID hashes subject, collector, `collected_at` and content, so re-collecting identical content creates a new node. The `sha256` field stays a pure content hash.
- **Time-dependent state is derived (D5).** Evidence freshness and `APPLIES_TO.status` are computed by pure functions that take an explicit `as_of`. `rules/` and `assess/` never call `now()`. The snapshot records its `as_of`.
- **Derived links have no STRM type (D6).** Composing two spokes yields "related via VC-xxx", with both spokes and the weaker strength shown. `no_relationship` mappings never compose. The definitions are re-checked against NIST IR 8477 on csrc.nist.gov in M4.

## Alternatives
Composing STRM types by table (for example subset ∘ superset). Rejected: two subsets of one control need not overlap, so any composed type would overstate the relationship.

## Consequences
- The UI shows more states and fewer green ticks, which is the product's point.
- Derived links are weaker claims than direct mappings, and are labelled that way.
