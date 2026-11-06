# 0031 — M10 dashboard: one data path, no derived governance in the UI, and a build that cannot carry a fixture
- **Status:** Accepted (2026-11-06). The owner approved these decisions when PR 62 merged ([plan](../m10-m11-plan.md)). They refine [0006](0006-static-snapshot-demo.md) and [0029](0029-m9-snapshot-export.md), and both stay in force.

## Context
M10 builds the dashboard that reads `snapshot.json`. Stage 4 says "three slices" but never defines them, and the ADRs leave these points open. The only snapshot that exists is the recorded fixture, and it has gaps: no ChangeEvent, no discovered record, and 874 of 928 requirement statuses `not_met`, nearly all from missing evidence. A live snapshot does not exist until M8 and M9 close, so M10 cannot close yet.

## Decision
1. **The UI derives no governance result.** It joins, filters, groups and counts. It never computes a status, finding, severity, applicability, freshness or crosswalk; it reads them from the snapshot (0029, decision 10). Only audit trails and `stale_by_change` follow edges in TypeScript, and each has a test against Python's answer.
2. **One data path.** One loader fetches `${import.meta.env.BASE_URL}data/snapshot.json`. The file is never imported or bundled. A `schema_version` other than 1 shows an error screen. A Content-Security-Policy meta tag sets `connect-src 'self'`, so the browser enforces this. No CDN, external font or analytics. A test fails if any other file calls `fetch` or imports a snapshot.
3. **A fixture cannot reach the publish path.** CI runs `--require-live` on every `web/public/data/*.json`, so a fixture cannot go there. `npm run fixture` writes `web/.fixture/snapshot.json` (ignored by git), and a Vite plugin with `apply: 'serve'` serves it at `/data/snapshot.json` in development only. A build test asserts that `dist/data/` holds no snapshot. 0029's rejection of a fixture for the public demo stands.
4. **A generated, invented test snapshot fills the fixture's gaps.** `web/src/test/mini-snapshot.json` holds a ChangeEvent, a `discovered` record and Evidence on both sides of the change. A script writes it from a small invented Python graph through the export code, and Python's `stale_by_change` answer beside it. A pytest checks that both files are current and that the snapshot validates against the `Snapshot` model, so it cannot drift. All its data is invented.
5. **A banner for anything but live.** When `data_source` is not `live`, every page shows "Recorded fixture: simulated, nothing read from AWS".
6. **No single compliance score.** No percentage, gauge or average anywhere (0005). The Overview explains that most requirement statuses are `not_met` because evidence is missing, and shows findings by code.
7. **No obligation timeline.** Obligation dates are not in the snapshot, and CLAUDE.md forbids hard-coding them. Adding one would be an export change, so it is out of M10.
8. **The History tab states its limit.** `H#` history is not published. The tab shows ChangeEvents and DiscoveryRuns, and says so. A system with no AWS resource gets an empty state that explains why.
9. **Badges.** A `Record<Source, Badge>` covers all six `Source` values, so a new value fails the typecheck: Live-discovered, Declared, Seeded, Synthetic, Derived, Simulated. A derived row's `simulated` flag shows its own Simulated badge beside Derived (0030).
10. **Relative base path.** Vite `base: './'` with hash routing works on Pages and in preview, with no 404 page.
11. **Phone width is tested.** Playwright at 390 px checks that no route scrolls sideways. The graph shows a list at that width.
12. **Audit-trail parity goes through the redaction's ID map.** Redaction rebuilds 15 of 23 Evidence IDs and their hashes (0029, decision 6). A script computes Python's `audit_trail` on the unredacted fixture graph and maps Evidence IDs and hashes through `Built.redacted.evidence_ids` to the published ones. TypeScript never rewrites IDs.
13. **Packages.** Exact versions, `npm ci --ignore-scripts`. The build and tests must work without install scripts.

## UI duties
Each duty in the plan's table has a test in `web/src/`, and its wording is not softened. The boundary note for VC-060 on `support-assistant` says IAM's simulator shows the boundary denies the call and that no live call was tried. It replaces the wording in [0025](0025-m8-deploy-and-crawl.md), per [0028](0028-m8-review.md), decision 5.

## Alternatives
| Option | Why not chosen |
|---|---|
| Import `snapshot.json` into the bundle | A fixture could ship, and the file would be in two places |
| Compute statuses and crosswalks in TypeScript | A second implementation that can drift (0029) |
| Serve the fixture in production builds | A demo that shows invented data as the estate |
| A compliance score on the Overview | An average hides the evidence gaps the product exists to show (0005) |
| An obligation timeline | Needs dates in the snapshot, which is an export change |
| Rewrite Evidence IDs in TypeScript | Another way for the audit trail to drift |

## Consequences
- The dashboard cannot show anything the snapshot lacks: `H#` history, obligation dates and usage records stay out.
- On the fixture, the Overview is mostly red. That is the data, and the page says why.
- M10 stays 🔄 until the Pages URL works from a live snapshot. The deploy workflow is proved only then.
- The owner asked for the plan's five PRs (A to E) as one PR. The scope is unchanged; the review is larger.
- `npm audit` reports moderate advisories in dev tooling (typescript-eslint's `minimatch`). Nothing in it ships. M11's security review owns them.
