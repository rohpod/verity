# 0034 — M11 close decisions: what is deferred, what is dropped, and what stays as it is
- **Status:** Proposed (2026-11-07). Refines [0008](0008-governance-as-code.md), [0028](0028-m8-review.md) and [0033](0033-m9-live-snapshot.md); all stay in force. Opus confirms it in the final M11 review. M11 is not marked done by this ADR.

## Context
M3, M8 and M9 are closed. M10 needed one more thing: the Pages URL on the live site. The M11 close register in [Stage 4](../stage-4-milestones.md) lists items that nobody had decided. Each decision below gives the reason, and each is a scope choice, not a change to content. Nothing here changes any EU AI Act or ISO content, date or wording. Bedrock and OpenAI are still mock-only. No AWS call was made for this ADR.

## Results: the Pages check (M10)
Measured on 2026-11-07 against `https://rohpod.github.io/verity/`, with a throwaway Playwright script kept out of the repository, at 1280 px and at 390 px.

| Step | Measured | Held? |
|---|---|---|
| Pages run for PR 72 | `build` and `deploy` both ran and passed (run 42373401481) | Yes |
| First check at 390 px | **Failed.** `#/graph` was 399 px wide. The "Start from" selector took the width of its longest option, and the live snapshot has 240 start nodes with ids up to 47 characters. The recorded fixture has shorter ids, so no earlier phone test saw it | **No** |
| Fix | PR 73: `max-w-full` on the selector and its label, and a Playwright test that adds a long option and fails without the fix (63 px over). Run 42376760265: `build` and `deploy` passed | Yes |
| Second check | Every route at both widths: 0 sideways overflow (the Graph page is 390 px at 390 px). Every page shows `data source: live` and `Snapshot as of 2026-11-07 12:20:39 UTC`, with no fixture banner, no console error and no off-origin request | Yes |
| Content | Provenance badges on every route that lists records. The boundary note ("IAM's policy simulator shows the permissions boundary denies this call. No live call was tried.") shows in Support Assistant > controls & evidence and in Controls > VC-060, where VC-060 is not implemented. The graph draws at 1280 px and is a list at 390 px, and its lists show badges including Synthetic. "What in this snapshot is not real" opens with 8 items, including the mocks. A direct link to a system opens in a new page | Yes |

## Decision
1. **N21, Bedrock's 8 other `Invoke*` actions: deferred.** No role grants them. Adding them to `ai_signals.yaml` changes the crawler's hash and needs a redeploy.
2. **N31, risk treatment decisions: dropped from scope,** because nothing reads them. This narrows [0008](0008-governance-as-code.md): the decision types it names that nothing reads are not built.
3. **N32, the three obligation dates no rule reads** (`euaia-omnibus-in-force`, `euaia-art5-new`, `euaia-high-risk-annex-i`): they stay as data and the question is deferred. Their content is not touched.
4. **N33, Art. 4a and the bias-test control: deferred, with no content change.** Kestrel records no special-category processing ([0019](0019-m5-rules-and-assessment.md)). Revisit if that changes.
5. **N34, D15: the stated reason overstated it.** Policy, Dataset, Candidate and DiscoveryRun appear in none of the 5 traversals. The node types stay, because other views need them. This is the correction, and D15 itself is not edited.
6. **N25 and N26, re-seed: deferred.** No re-seed is planned, and none may run until pruning is decided (re-seeding removes nothing, so a deleted mapping stays open). The time of a re-seed is unmeasured.
7. **E4, CycloneDX: dropped.** Nothing built uses it.
8. **E5, ISO 27001 Amendment 1: deferred.** The standard was not read ([0018](0018-unread-standards.md)), and the content records what public sources say.
9. **N23: the CLI message is fixed, and the `credential_process` fix is deferred.** The message that blamed throttling is replaced, because [0028](0028-m8-review.md) found the slowness came from credential refreshes. The `credential_process` fix would touch code that goes into the zips, and few live runs remain. Operators should expect slow live runs when using `aws login` credentials.
10. **R1, `npm audit`: deferred.** All 7 advisories are dev tooling (Dependabot alert 1 is `minimatch`, scope `development`, and it is still open). `npm audit --omit=dev` found 0 vulnerabilities on 2026-11-07, so nothing that ships is affected.
11. **Final snapshot.** The snapshot from PR 72 (`as_of` 2026-11-07T12:20:39.767Z) is the final one unless the owner asks for a refresh. It predates the 2 Dec 2026 date changes, so a later export would differ. The hard deadline of 1 Apr 2027 for the last live snapshot is met by it. A refresh needs the owner's approval and uses the runbook.
12. **Teardown.** Keep the estate until after submission, then run `tofu destroy` in the second half of April 2027, before the plan ends on 4 May 2027. This permanently deletes the DynamoDB table and its data, and the committed snapshot stays as the record. The plan is never upgraded. The destroy itself still needs the owner's approval then, with what it removes, its price and the undo.

## Alternatives
| Option | Why not chosen |
|---|---|
| Build risk treatment decisions | Nothing reads them, and they add content to review |
| Add the 8 `Invoke*` actions now | It redeploys the crawler for a grant no role has |
| Fix `credential_process` now | It touches zip code, for the few live runs left |
| Refresh the snapshot now | It would add nothing: the 2 Dec 2026 dates have not taken effect |
| Fold the Graph fix into the M11 PR | Kept as its own PR (73) so the Pages re-check followed a deploy of just that fix |

## Consequences
- **Not proved:** a run on `cron(0 3 * * ? *)`, and a credit read at or after 10:12 UTC on 2026-11-08 ([0032](0032-m8-scheduled-run.md), [0033](0033-m9-live-snapshot.md)). The docs still do not say the schedule runs daily.
- **Dates not re-verified here.** Obligation dates are data with `source_url` and `last_verified`. Re-verifying them is the final review's step, and nothing here changed one.
- **Known limit, unchanged:** the listed fields and scan rules cannot prove nothing sensitive exists beyond them ([0030](0030-m9-redaction-review.md)).
- **After the 2 Dec 2026 changes,** a later snapshot would differ from the published one.
- **The register's Status column stays "draft: Opus to confirm".** M11 is not marked done.
