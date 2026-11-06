# M10 and M11 implementation plan

_2026-11-06. Written by Opus for hand-over. Inputs: [Stage 4](stage-4-milestones.md), [architecture §I and §J](architecture.md), [ADRs](adr/), [open milestones](open-milestones.md). `main` at PR 61._

## Order of work

M10 can start now, because it builds against the fixture. It cannot close until a live snapshot exists.

| Track | Work | Lead | Blocked by |
|---|---|---|---|
| A | L15, first scheduled run, credit read: closes M3 and M8 | Owner, with approval per step | Nothing. Evidence starts expiring around 29 Nov |
| B | M9 PR C code: live export and commit SHA lookup | Sonnet | Nothing |
| C | M10 PRs A to E | Sonnet | Nothing |
| D | M9 live run and snapshot PR: closes M9 | Sonnet runs it, Opus reviews, owner merges | Tracks A and B |
| E | M10 close: Pages URL works | Sonnet | Tracks C and D |
| F | M11 | Opus, with Sonnet steps below | M8, M9 and M10 ✅ |

One branch at a time, as CLAUDE.md requires. Do Track B first: it is small, and it keeps the critical path clear.

## M10 decisions (record in ADR 0031 with PR A)

"Three slices" was never defined, and these points are not settled by the ADRs. These are the proposals, and the ADR records the owner's answer.

1. **The UI derives no governance result.** It joins, filters, groups and counts. It never computes a status, finding, severity, applicability, freshness or crosswalk. It reads them from the snapshot ([ADR 0029](adr/0029-m9-snapshot-export.md), decision 10). Only audit trails and `stale_by_change` follow edges in TypeScript, and each has a test against Python's answer.
2. **One data path.** One loader fetches `${import.meta.env.BASE_URL}data/snapshot.json`. The file is never imported or bundled. It refuses a `schema_version` other than 1 with an error screen. A Content-Security-Policy meta tag sets `connect-src 'self'`, so the browser enforces this. No CDN, external font or analytics.
3. **Fixture data stays out of the publish path.** CI runs `--require-live` on every `web/public/data/*.json`, so a fixture cannot go there.
   - `npm run fixture` runs `uv run verity export --local --as-of 2026-11-06T00:00:00+00:00 --out web/.fixture/snapshot.json`. Git ignores `web/.fixture/`.
   - A Vite plugin with `apply: 'serve'` serves that file at `/data/snapshot.json` in development only. It is never in a production build.
   - A build test asserts this, and ADR 0029's rejection of a fixture for the public demo stands.
4. **A hand-built test snapshot fills the fixture's gaps.** The fixture has no ChangeEvent and no `discovered` record, and it is `data_source: fixture`. A small file at `web/src/test/mini-snapshot.json` covers these. A pytest test validates it against the `Snapshot` model, so it cannot drift. All its data is invented.
5. **A banner for anything but live.** When `data_source` is not `live`, every page shows a persistent "Recorded fixture: simulated, nothing read from AWS".
6. **No single compliance score.** No percentage, gauge or average anywhere ([ADR 0005](adr/0005-control-assessment-assurance-ladder.md)). On the fixture, 874 of 928 requirement statuses are `not_met`, nearly all from missing evidence, so the Overview must explain that and show the findings by code.
7. **No obligation timeline.** Obligation dates are not in the snapshot, and CLAUDE.md forbids hard-coding them. Adding one would be an export change, so it is out of M10.
8. **The History tab is honest about its limit.** `H#` history is not published. The tab shows ChangeEvents and DiscoveryRuns, and says so. Systems with no AWS resource show an empty state that explains why.
9. **Badges.** A `Record<Source, Badge>` covers all six `Source` values, so a new value fails the typecheck: Live-discovered, Declared, Seeded, Synthetic, Derived, Simulated. The `simulated` boolean on derived rows shows its own Simulated badge next to Derived ([ADR 0030](adr/0030-m9-redaction-review.md)).
10. **Relative base path.** Vite `base: './'` with hash routing works on Pages and in preview, with no 404 page.
11. **Phone width is tested.** Playwright at 390 px checks that no route scrolls sideways. The graph shows a list at that width.

## UI duties from the ADRs

Each row needs a test. Use this wording in substance, and do not soften it.

| Where | Duty | Source |
|---|---|---|
| Every view | Provenance badges, and the snapshot timestamp | Architecture §J, ADR 0006 |
| Every page | `header.simulated_components` is reachable, and synthetic records say so | ADR 0030, decision 8 |
| Requirement views | Show `verified_against` beside ISO requirements, and explain why they never go green | [ADR 0018](adr/0018-unread-standards.md) |
| Requirement views | ISO: IDs and original summaries only | CLAUDE.md |
| Crosswalk | Show rationale and the "derived" label. A derived link has no STRM type: show `from_strm`, `to_strm` and the control it goes through. Never show two requirements as equal | [ADR 0004](adr/0004-hub-and-spoke-strm-crosswalk.md), [ADR 0010](adr/0010-assessment-and-crosswalk-semantics.md) |
| Crosswalk | Label strength as a Verity convention taken from the Secure Controls Framework, not from NIST | [ADR 0017](adr/0017-m4-content-semantics.md) |
| Controls | Show status, level and freshness together, never a bare tick | ADR 0005 |
| Controls | Label demo L4 results *simulated sign-off* | D11 |
| Evidence | Where `redacted: true`, say the hash covers the published content, not the stored original, and cannot be checked against the live table | ADR 0029, decision 6 |
| VC-060, `support-assistant` | Say IAM's simulator shows the boundary denies the call, and that no live call was tried. Never say the grant "is ineffective". This replaces the wording in [ADR 0025](adr/0025-m8-deploy-and-crawl.md) | [ADR 0028](adr/0028-m8-review.md), decision 5 |
| Providers | Show `Provider.simulated`. Never suggest Bedrock or OpenAI were invoked | [ADR 0007](adr/0007-mock-only-ai-providers.md) |
| Discovery | Show the signals that fired, so the UI explains why | Architecture §D |
| System views | Show organisation-level controls as inherited | Architecture §L |
| About | "Not legal advice" and "mappings are the author's interpretation" | README |

## M10 pull requests

Each PR starts from an updated `main` and waits for the merge before the next one.

### PR A: `feat/m10-foundation`
- ADR 0031, and the architecture §K and Stage 4 D-table entries.
- Vite, React, TS strict, Tailwind and shadcn/ui in `web/`, with the §J libraries added only in the PR that uses them. Exact versions, and keep `npm ci --ignore-scripts`. If a package needs an install script, stop and ask.
- Loader, `SnapshotProvider` with indexes built once (by ID, edges by `src` and `dst`), and a helper for open records. Read `graph/loader.py` first and match how Python treats closed edges and `valid_to`.
- Shell: hash routes for all six screens, timestamp, data-source banner, simulated-components panel, `ProvenanceBadge`, error and empty states, MiniSearch box.
- The fixture flow and mini snapshot from decisions 3 and 4.
- CI: generate the fixture, then typecheck, lint, unit tests, build, and assert `dist/data/` holds no snapshot. Keep the existing contract check working.
- **Done when:** every route renders from the fixture with its timestamp and badges, and a test fails if any file other than the loader calls `fetch` or imports a snapshot.

### PR B: `feat/m10-registry` (slice 1)
- Overview: systems by source, findings by severity and code, requirement states by framework, the assurance ladder, the Candidates count. Load the `dataviz` skill before the charts.
- AI Registry with TanStack Table, and the Candidates inbox with signals.
- System profile with its seven tabs: summary, components, data, risks, obligations, controls & evidence, history.
- **Done when:** `shadow-summariser` appears as a high Candidate with its signals, `support-assistant` shows the VC-060 failure and boundary note, and Talent Screening shows the bias-test gap.

### PR C: `feat/m10-assurance` (slice 2)
- Controls & evidence: the assurance ladder per control and scope, freshness, the Evidence detail, and the audit trail.
- Risk register. Crosswalk explorer from `crosswalk` rows and `MAPS_TO` edges.
- **Audit trail parity:** a script writes Python's `audit_trail` results for a set of requirement and scope pairs to `web/.fixture/`, and a test compares them. Trap: 15 of 23 Evidence IDs change in the fixture, so compare through the redaction's old-to-new map. If that map is not reachable, stop and ask. Do not rewrite IDs in TypeScript.
- **Done when:** the audit trail matches Python and the UI duties for these screens pass.

### PR D: `feat/m10-graph` (slice 3)
- Graph explorer with Cytoscape and fcose, loaded lazily. Start from a chosen node's neighbourhood, and hide the 433 ControlAssessments by default.
- "Impact of…" mode from `provider_impact`, including the empty case for in-house models.
- `stale_by_change` view, tested on the mini snapshot: only evidence with `collected_at` before `detected_at` is stale.
- Playwright: every route at 390 px and at desktop width, plus deep links.
- **Done when:** impact and stale views match their expected results, and no route scrolls sideways at 390 px.

### PR E: `ci/m10-pages`
- `.github/workflows/pages.yml`. Pages is already set to `build_type: workflow`, so no repository setting changes.
- Trigger on pushes to `main` that touch `web/`. `pages: write` and `id-token: write` on the deploy job only. No secrets and no AWS credentials.
- If `web/public/data/snapshot.json` is missing, skip with a notice.
- Build, then run `verity export --check dist/data/snapshot.json --require-live` on the exact bytes to be published, then deploy.
- Update the README status line, which still says nothing is deployed, and add the demo link. Update architecture §J.
- **Done when:** the workflow skips cleanly with no snapshot. Its deploy path is proved in Track E.

### Close (Track E)
After the snapshot PR merges: open the Pages URL at desktop and phone width, check every route and the live timestamp, and confirm no fixture banner shows. Add an M10 close-out to Stage 4 and mark M10 ✅.

## M11 plan

M11 is **Opus-led** in Stage 4, and it stays that way. Sonnet does the steps marked below and stops at the rest.

| # | Step | Lead |
|---|---|---|
| 1 | Build the close register in Stage 4: all 6 §L items, every ❓ in Stage 2 and the ADRs, and every open row in "Notes for later milestones". Each is closed, with its source, or explicitly deferred, with a reason | Sonnet drafts, Opus confirms |
| 2 | Fix `credential_process` running on every operator call, and the CLI's "while it throttles" message (ADR 0028). This shortens every later live assess | Sonnet |
| 3 | Decide the open notes: Bedrock's 8 other `Invoke*` actions, risk treatment decisions (ADR 0008), re-seed pruning, the three unread obligation dates, Art. 4a, the D15 wording | Opus |
| 4 | Docs repair: add ADR 0027 to the architecture §K log, where it is missing, correct the §I line on live export, and match the README's real-vs-simulated table to what was built | Sonnet |
| 5 | Security review: IAM against the deployed state, workflow permissions, the CSP, `npm audit`, Python dependency audit, git history for secrets and account IDs, the published snapshot | Opus |
| 6 | ADR review against the code. Record gaps in a new ADR, because accepted ADRs are not edited | Opus |
| 7 | Write `docs/runbooks/m11-final-snapshot.md` | Sonnet |
| 8 | Final snapshot. **Start by 15 Mar 2027**, for a hard deadline of **1 Apr 2027** | Sonnet runs it, Opus reviews, owner merges |
| 9 | Teardown decision and any teardown | Owner, on Opus's recommendation |
| 10 | M11 validation, and mark it ✅ | Opus |

**Before the final snapshot.**
- `euaia-art50-2-legacy` and `euaia-art5-new` take effect on 2 Dec 2026, so a later snapshot can differ from an earlier one. Review the difference and do not assume it is a fault.
- Re-verify EU AI Act dates and `last_verified` values, because the law may have changed. Any change is an Opus task.
- Crawler evidence renews about every 22 days, and each renewal needs a fresh `verity assess --target dynamodb` before export. Confirm the schedule stayed `ENABLED`, because a plain `tofu apply` resets it.
- Every step that writes to AWS needs its own approval.

**Teardown, recommended by Opus, decided by the owner.** Keep the estate until the final snapshot is live and checked on Pages. Then run `tofu destroy` in the second half of April 2027, before the plan ends on **4 May 2027**. This permanently deletes the table, and the Pages snapshot becomes the only record. The plan must never be upgraded. Record the decision in an ADR and in the README.

## Rules for the hand-over

- No AWS call of any kind during M10 PRs A to E.
- Stop and tell the owner to switch to Opus for: anything that needs an export or schema change, a new ADR beyond 0031, wording about regulation or the boundary beyond the table above, any change to IAM, or a bug that defeats two fixes.
- Never mark a milestone ✅ until its criteria pass.
