# 0012 — Graph schema refinements before implementation
- **Status:** Accepted (2026-11-05). Refines [0003](0003-dynamodb-graph-repository.md), [0004](0004-hub-and-spoke-strm-crosswalk.md), [0005](0005-control-assessment-assurance-ladder.md) and [0010](0010-assessment-and-crosswalk-semantics.md); all stay in force.

## Context
Planning M1 meant walking the §E schema and §H key design against the use cases again. That exposed cases where data would be silently lost or a traversal would give a wrong answer. Fixing them now costs a document edit. After M2 they would mean a data migration.

## Decision
**Edge identity and history**
- **Qualifier in edge identity.** Stage 1 requires applicability per (system, role), but `E#{type}#{dst}` holds one edge per triple, so a second role would overwrite the first. Edge keys become `E#{type}#{dst}#{qualifier}` and `R#{type}#{src}#{qualifier}`. The qualifier is derived from `role` on `APPLIES_TO` and `purpose` on `PROCESSES`. The other 25 edge types have none and keep the shorter key.
- **Closed intervals.** An edge item holds one `valid_from`/`valid_to`, so an edge that closes and reappears would lose its earlier interval. Reopening moves the old interval into a `closed_intervals` list on the same item. Point-in-time queries check the current interval and that list. Intervals are half-open: `[from, to)`. Edge property history is not kept.
- **Collision-free sort keys.** `H#{iso_ts}` and `U#{iso_ts}` collide when two writes share a timestamp, which concurrent Lambdas can do. They become `H#{iso_ts}#{version}` and `U#{iso_ts}#{usage_id}`. `usage_id` is a uuid4 created once by the caller, so a retried write is idempotent.

**Organisation lookup**
- **The tenant is the organisation.** §E has no edge from `AISystem` to `Organisation`, and the owner → department → organisation path fails for an unowned system. Each tenant has exactly one `Organisation`, enforced on write, and traversals look it up by type.

**Evidence**
- **Staleness has a cutoff.** A `ChangeEvent` affects only evidence with `collected_at` earlier than its `detected_at`. Without this, a resource that changed once could never have fresh evidence again.
- **Evidence has a subject.** D4 hashes a subject, so `Evidence.subject` is a required field, matched by an `ABOUT` edge. The ID covers content through `sha256`, which works for both inline content and `content_ref`.

**Crosswalk and assurance**
- **`no_relationship` has no strength or sufficiency.** Both must be empty for that STRM type and are required for the others, so such a mapping can never count towards *Satisfied*.
- **Only technical controls can be automatable.** A control with `kind` organisational or legal_documentary cannot set `automatable: true`. Otherwise the [0005](0005-control-assessment-assurance-ladder.md) guardrail could be bypassed through content.

**Added by the end-of-M1 review**
- **`source_version`, not `version`.** `Requirement` and `Framework` hold the legal text's version in `source_version`, because `version` is the record revision counter on every node.
- **An unknown provider is a gap.** A provider-level control is *Not applicable* only when every model of the system is known to be in-house (D13). No recorded model, or a third-party model with no `PROVIDED_BY`, gives `provider_unknown`.
- **Past queries use past versions.** `load_graph(as_of)` builds each node from the version the graph held then, so a past status is the status of that date.
- **`valid_to` cannot be in the future.** `as_of=None` means "open" and reads no clock, so a future end would make a record vanish early.
- **Ending a node closes its edges.** An open edge to an ended node is refused, so `neighbors` and `load_graph` agree.
- **Re-seeding is safe.** Sending the same closed edge again changes nothing. An open edge sent for a closed one reopens it, and a `valid_from` earlier than the close is treated as stale, so periods never overlap.
- **Reads return copies.** Frozen models still hold mutable dicts, so a repository never hands out what it stores.

## Alternatives
| Option | Why not chosen |
|---|---|
| List-valued `roles` and `purposes` on one edge | `rule_id`, `reason` and `in_force_from` can differ per role, and `close_edge` could not close one role alone |
| Overwrite the interval when an edge reopens | Point-in-time answers would be wrong for any edge that flapped, which breaks the §H promise |
| Refuse to reopen a closed edge | Pushes the problem onto the crawler and rules engine, and breaks idempotent re-crawls |
| New `AISystem OPERATED_BY Organisation` edge | A 28th edge type that every seed and promotion must write, with no MVP use beyond this lookup |
| Resolve the organisation through the owner | An unowned system would silently lose all its org-level obligations |

## Consequences
- `close_edge` takes an optional qualifier, and M2 must update both the `E#` and `R#` items.
- Moving to several organisations per tenant later would need an explicit edge.
- `ChangeEvent` timestamps depend on crawl order: M6 stamps `detected_at` at run start, so evidence collected in the same run survives.
- `content_hash`, used to detect real changes, excludes `created_at`, `updated_at` and `version`.
