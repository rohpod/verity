# 0029 — M9 snapshot export: fail-closed redaction, rebuilt hashes and a generated contract
- **Status:** Accepted (2026-11-06). Refines [0006](0006-static-snapshot-demo.md) and [0022](0022-m6-review-fixes.md); both stay in force.

## Context
`verity export` writes the only file the public demo reads, and a commit to a public repository cannot be taken back. Planning M9 against the live graph (read-only, counts only) found:
- **The graph is cleaner than expected.** 664 nodes and 1,307 edges hold no raw account ID, no Function URL and no canary. The only account data is one `acct_` digest, the owner's, in 17 `config_snapshot` Evidence items.
- **Swapping digests for ordinals is not enough.** `Evidence.sha256` and `config_hash` are computed over content that includes the digest, and `Evidence.id` is computed from `sha256`. With the rest of the content public, anyone can try all 2^32 digests offline and match a published hash. That recovers the digest, which narrows the account to a few hundred candidates, the exposure ADR 0022 set out to remove.
- **Simple scans would misfire.** A hex hash can hold a run of 12 digits (one `file_sha256` does), and `crawler@0.1.0` looks like an email to a loose pattern.
- **Evidence validates its own hash,** so an edited copy cannot be a valid `Evidence`.
- **Findings are not stored.** They exist only as the output of an assessment.
- **The five traversals are Python.** The dashboard cannot run them, and rewriting them in TypeScript would create a second implementation that can drift.

## Decision
1. **`verity export` has two sources, and the file says which.** The default reads the live graph through `GraphRepository.load_graph()`, read-only. `--local` crawls the recorded fixture into memory and assesses it, with no AWS access. The file carries `data_source: live | fixture`. No new AWS service, permission or boto3 file is needed, and M9 changes nothing on AWS.
2. **Export refuses a stale graph.** It runs `estimate_apply` at one `as_of`, and refuses if that would write anything: the stored assessments must be the ones published. Findings and statuses come from that same run.
3. **A public field is listed, not assumed.** `export/` holds an explicit list of public fields for each node and edge model, and the snapshot models are built from it. A test fails if a model has a field that is neither public nor withheld, so a new field is never published by default.
4. **The hash fields derived from raw config are withheld.** `config_hash`, `previous_config_hash` and `new_config_hash` are left out, and so is `config_hash` inside Evidence content. The UI needs only that a change happened.
5. **The own account becomes `000000000000`, and any other account an ordinal.** The own digest comes from `own_account`. Others become `acct_1`, `acct_2` in order of first appearance, walking records in sorted order. Live has none today, but the fixture path must prove it.
6. **Evidence changed by redaction is rebuilt.** It goes through `Evidence.build` from the redacted content, so `sha256` and `id` are new and every reference follows through one old-to-new map. The record carries `redacted: true`, and the UI must say the hash covers the published content, not the stored original. Unchanged Evidence keeps its hash and ID.
7. **An independent scanner has the last word.** It shares no code with the redaction and runs on the serialised output, walking parsed JSON values and keys. A hit means nothing is written. It reports the category and JSON path, never the value. Output goes to a temporary file and is renamed only after the scan passes. It refuses:

   | Category | Rule |
   |---|---|
   | Account ID | Any run of 12 digits except `000000000000`, ignoring values that are wholly a hash (`^[0-9a-f]{64}$`, or `ev:` and hex) |
   | Digest | `acct_` followed by 8 hex digits |
   | Function URL | `lambda-url.`, `.on.aws` or `execute-api.` |
   | Email | `@`, a domain and a letters-only ending, so `crawler@0.1.0` passes |
   | Canary | The D1 canary text |
   | Identity and paths | `:user/` in an ARN, `/Users/`, `/home/` |
   | Old hashes | Any `sha256` or Evidence ID replaced in decision 6 |

   `verity export --check FILE` runs the same scanner, and CI runs it on any committed snapshot. Old hashes need the graph, so `--check` cannot test them.
8. **Env values are proved by construction and a canary.** The graph stores names only, and a canary test runs through the fixture to the file. Export never reads env values, in line with the rule on the crawler. The estate's other values are in `infra/modules/estate/locals.tf` and are public already. The one derived value, the Function URL, has its own scan rule.
9. **Commit SHAs are looked up at export (D10).** For each decision, walk `git log --format=%H -- <path>` and take the oldest commit whose file matches `file_sha256`. Only the SHA is read, never an author. A live export refuses if one is missing. A fixture export writes `null`.
10. **What the dashboard cannot derive is precomputed.** The file holds `nodes`, `edges`, `findings`, requirement statuses, control results, `obligations` per system, `provider_impact` per provider and `crosswalk` per framework pair. Audit trails and `stale_by_change` follow edges, so M10 can read them from `edges`. `H#` history and `U#` usage records stay out.
11. **Every record carries provenance, and the file carries the context.** Nodes and edges keep `source`. Findings, statuses and precomputed rows are `derived`. The header holds `schema_version`, `as_of`, `data_source`, the redaction steps applied and the simulated components (`mock-bedrock`, `mock-openai`, simulated sign-offs). The same inputs and `as_of` give identical bytes.
12. **The contract is generated in one direction.** `snapshot.schema.json` comes from the snapshot models, and `snapshot.ts` from that schema with `json-schema-to-typescript`, at an exact version in a minimal `web/package.json`. Both files are committed, and CI regenerates them and fails on a difference. M10 owns the rest of `web/`.
13. **A live snapshot is published only by a reviewed PR.** It goes to `web/public/data/snapshot.json`. Opus reviews the redaction and the owner confirms before merging. It comes after M8 closes, because L15 will deploy a new crawler and the scheduled run will change what the file should show.

## Alternatives
| Option | Why not chosen |
|---|---|
| Ordinals only, as ADR 0022 planned | Published hashes still reveal the digest |
| Drop `sha256` and IDs from redacted Evidence | Breaks every reference and the audit view |
| Publish a keyed hash of the original | Needs a secret to store, and a reader could verify nothing |
| Blocklist of withheld fields | A new field would be published by default |
| Scanner built on the redaction's patterns | One mistake would then pass both |
| Compare against real env values and the account ID | Export would have to read the values, and it adds an STS call. The patterns already cover both |
| Rewrite the traversals in TypeScript | A second implementation that can drift |
| Commit a fixture snapshot for the public demo | The demo is meant to show the real estate |

## Consequences
- A published hash for redacted Evidence cannot be checked against the live table. This is the point, and the UI must say so.
- Evidence IDs differ between the graph and the snapshot for those items.
- Export can be refused for a reason outside its control: a crawl that changed anything requires `verity assess` first.
- Live JSON is about 740 KB before precomputed rows. The file must stay under 2 MB, measured in M9.
- CI gains Node, for the type generation only.
- **Not proved by M9:** that nothing sensitive exists beyond the scanner's patterns. The field list limits what can appear, and the Opus review is the last check.
