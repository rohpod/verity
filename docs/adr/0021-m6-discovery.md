# 0021 — M6 discovery: what the crawler writes, and what it never touches
- **Status:** Accepted (2026-11-06). Refines [0012](0012-graph-schema-refinements.md), [0014](0014-m2-measurements-and-evidence-cap.md) and [0020](0020-m5-review-fixes.md); all stay in force. It closes ADR 0014's open question about evidence growth and its evidence-cap measurement.

## Context
M6 builds the discovery pipeline of architecture §D. Planning it raised questions that the earlier documents left open:
- **Growth.** ADR 0014 estimated 19,000 to 35,000 items after 150 daily crawls, mostly from Evidence written on every run.
- **The 16 KB cap.** It was set from fixtures. A role with long policies can pass it, and `content_ref` is a git file that a Lambda cannot write.
- **D1.** `ListFunctions` returns env var values, and ARNs hold the account ID. Both must stay out of every record, log and error.
- **Seeded facts.** M4 seeded the `AISystem` facts (`roles`, `use_domains`, and the others in ADR 0017). A crawler that wrote systems could overwrite them.
- **Provider links.** §D says "system → provider", but §E only has the path through Model.
- **Time.** `ChangeEvent.detected_at` and `Evidence.collected_at` must compare the right way round, and a re-crawl must not write history.

These decisions make no AWS changes. M6 reads nothing from AWS: every AWS path is tested with `moto` or a stub, and the live path is M8.

## Decision
1. **Evidence and `OBSERVED` are written on change only.** A resource gets a `config_snapshot` when it is new, when its `config_hash` differs from its latest snapshot's, or when that snapshot has 8 days or less to run. An `OBSERVED` edge is written only for a new or changed resource. `DiscoveryRun.summary` holds the per-run counts instead. Crawler evidence is valid for 30 days. 8 days is `EXPIRING_WITHIN` plus one, so a daily crawl refreshes before the low `evidence_expiring` finding fires, and a crawler that stops lets its evidence go stale, which is correct. For 150 daily crawls of 30 resources this is about 7 snapshots a resource, so about 1,000 Evidence items instead of 19,000 to 35,000.
2. **Evidence over the 16 KB cap is summarised, never refused.** The cap stays. `config_hash` always covers the full normalised config, so change detection is unaffected. Over the cap, the content becomes `{truncated: true, config_hash, ai_actions, statement_count}`. IAM allows about 10 KB inline and 6 KB per managed policy, so a role can pass the cap. `DiscoveryRun.summary.largest_evidence_bytes` records the size, and M8 reads the real figure from the first live crawl.
3. **One boundary cleans everything.** `discovery/boundary.py` turns each raw API dict into a frozen dataclass as it is received. Env var values are dropped there (D1). Twelve-digit account IDs in every kept string become `<account>`, so ARNs in evidence are safe for M9. Lambda `Description` is scored but never stored, because it is free text. Pydantic and exception messages never include raw dicts.
4. **Simulated data is labelled.** `FixtureCollector.source` is `Source.SIMULATED`, `AwsCollector.source` is `Source.DISCOVERED`, and every record of a run carries it. A fixture run never looks live-discovered, and simulated Evidence is counted apart by the existing `simulated` flag.
5. **Only Lambda functions are scored and become Candidates.** Roles and tables keep `ai_likelihood=None`. A role's IAM signal counts for the function that assumes it. Otherwise one workload would produce two Candidates.
6. **The crawler writes only** `AWSResource`, `Candidate`, `DiscoveryRun`, `ChangeEvent` and `Evidence` nodes, and `RUNS_ON`, `ASSUMES`, `CALLS`, `OBSERVED`, `AFFECTS`, `DERIVED_FROM`, `PROMOTED_TO`, `ABOUT` and `COLLECTED_FROM` edges. `persist` raises on any other type. It never writes an `AISystem`, which closes the M6 note on seeded facts.
7. **There is no system-to-provider link.** §E's path through Model stands. The crawler creates no `Provider`, `Model` or `USES_MODEL`. A provider hint stays a signal on the Candidate. A system with no model is already `provider_unknown` (D13). "Also system → provider" is removed from §D.
8. **`CALLS` comes from IAM resource ARNs only.** Env var names cannot name a target once values are dropped. `Resource: "*"` makes no edge, because fanning out would invent relationships. Wildcards inside an ARN are matched with `fnmatch` against the known ARNs.
9. **Capability without usage is VC-060, not a new finding.** For each system with at least one role reached through `RUNS_ON` then `ASSUMES`, the crawler writes one `automated_test` Evidence with `control: ctl:VC-060`, `scope: <system>`, `outcome`, `granted`, `unused` and `unparsed`. `outcome` is `fail` if any granted AI action has no matching CloudTrail event for that role. **Only CloudTrail counts here, never `U#` records.** The demo's usage records come from a mock, and the `bedrock:Converse` grant is never exercised, so counting them would hide the seeded finding. Row 1 of the control table then gives Not implemented at L3, and the existing `control_not_met` finding carries it. Only `Effect: Allow` counts. A `NotAction` statement is ignored and recorded as `unparsed: true`. The same write-on-change rule applies, compared on the content hash and on whether a resource it came from changed in this run.
10. **No other control is raised.** VC-003, VC-030, VC-031, VC-040, VC-041, VC-061 and VC-062 stay unassessed by the crawler. A `config_snapshot` names no control, so it never reaches the assessor.
11. **`shadow_ai_candidate` is a new finding**, derived on read: one per open Candidate with no open `PROMOTED_TO`. High for `declared` and `probable`, medium for `possible`. The subject is the Candidate.
12. **Candidate lifecycle.** A Candidate is created for a function not linked to a system that scores probable or possible, or whose tag or manifest names a system that does not exist (likelihood `declared`, signal `names_unknown_system`). It is ended with `valid_to` when it stops qualifying or its resource goes. If its resource becomes linked to a system it **stays open** with `PROMOTED_TO`, because an open edge to an ended node is refused (`endpoint_ended`). An upsert reopens it if it qualifies again.
13. **`ai:system-id` holds a full ID**, such as `sys:talent-screening`.
14. **Manifests** are YAML in SSM under `/verity/manifests/`: `{system: sys:x, resources: [{type: lambda, name: y}]}`, validated with pydantic. An invalid one never stops a run: it is counted in `summary.manifests_invalid` and reported. Publishing them is M8.
15. **Platform functions are excluded by tag.** A resource tagged `verity:component` (the mocks and the crawler) scores *none* with signal `platform_component`. Without this, `mock-openai` would become a shadow-AI Candidate.
16. **The ladder order stays as in §D:** declared, confirmed_usage, probable, possible, none. The strongest wins, and every signal that fired is stored, sorted.
17. **`boto3` may be used in `discovery/aws.py` as well as in `graph/dynamodb/`.** That file lists resources and is not graph access, so `GraphRepository` stays the only way to the table. The boundary test allows exactly that one file.
18. **Only `full` crawls exist.** `verity crawl` without `--local` is refused until M8. `incremental` is not built.
19. **Time.** `detected_at`, `collected_at` and `started_at` are all the run's one start time, read once. Evidence of the same run is therefore never stale (`collected_at < detected_at` is false). `valid_from` is left unset on re-crawls, so no history is written.
20. **A deleted resource** is ended with `valid_to`, which closes its edges, and gets no ChangeEvent. Its Evidence expires within 30 days.

## Alternatives
| Option | Why not chosen |
|---|---|
| Write Evidence and `OBSERVED` on every crawl | 19,000 to 35,000 items after 150 days, and a full scan of 2.5 to 4.5 minutes (ADR 0014) |
| Refuse evidence over the cap | One large role would stop the whole run |
| Raise the cap to fit | Only raising is safe, but the size is unmeasured. M8 reads the real figure |
| Store env var values, or hash them | The canary test (D1) would have nothing to prove, and a hash of a short secret can be guessed |
| Score roles and tables too | One workload would produce several Candidates |
| Count `U#` usage records in the VC-060 check | The mock writes them, so the unused `bedrock:Converse` grant would pass, and the seeded finding would vanish |
| A new finding code for unused permissions | VC-060 already means this, and a second path would give two answers |
| Fan `Resource: "*"` out to every resource | Invents relationships that nobody wrote |
| Link a system to a provider directly | A second route beside Model, and the two could disagree |
| Create the AISystem from a Candidate | Overwrites facts a person recorded, and a person decides what enters the registry |
| End a Candidate as soon as its resource is linked | The `PROMOTED_TO` edge would be refused (`endpoint_ended`), and the link would be lost |

## Consequences
- A function deleted from AWS is ended and gets no ChangeEvent. Evidence collected from it stays in the graph and expires within 30 days.
- A crawler that stops is visible: its evidence goes stale after 30 days and `evidence_expiring` fires 7 days before.
- The VC-060 check rests on CloudTrail event history, which keeps 90 days and may not show every Bedrock call. A grant used less often than that reads as unused.
- A role whose policy passes 16 KB is summarised, so the snapshot cannot show which statement changed. The hash still can show that something did.
- The crawler's own Lambda and the mocks must carry the `verity:component` tag. M8 adds it.
- The crawler needs the IAM actions listed in §D. M8 grants them, and `lambda:GetFunction` stays out.
- Descriptions are scored but not stored, so a Candidate cannot say that a description was the reason. It shows the `name_ai_token` signal only.
