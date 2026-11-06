# 0022 — M6 review fixes: AI actions, inconclusive checks, account digests and signal matching
- **Status:** Accepted (2026-11-06). Refines [0021](0021-m6-discovery.md), [0019](0019-m5-rules-and-assessment.md) and [0007](0007-mock-only-ai-providers.md); all stay in force, except where *Decision* 1 to 4 and 8 narrow 0021 and *Decision* 2 corrects 0007.

## Context
The end-of-milestone review of M6 passed the validation criteria, but reproduced cases where the crawler shows more assurance or less risk than it should, or stops. The fixture avoids all of them:
- **A broad role passes VC-060.** ADR 0021 ignored `NotAction` statements. A role shaped like `PowerUserAccess` therefore gave `outcome: pass`, which is Implemented at L3.
- **Real Bedrock use reads as unused.** AWS's Converse API reference says Converse "requires permission for the `bedrock:InvokeModel` action", and the user guide says ConverseStream needs `bedrock:InvokeModelWithResponseStream`. CloudTrail records the event name `Converse`, so matching the name to a grant failed. The seeded `bedrock:Converse` grant of ADR 0007 is not the permission Converse needs. We could not read the IAM action table to see whether the action exists at all.
- **A role's trust moving to another account is not seen.** Every account ID became `<account>` before hashing, so swapping one external account for another changed nothing.
- **Shadow AI is missed.** `LEGAL_OPENAI_API_KEY`, `AWS_BEDROCK_REGION` and `ContractSummariserFn` all scored *none*.
- **One name stops a crawl.** A 12-digit number in a function or env var name became `<account>`, which is not a valid ID part or env var name.
- **D1 fails at debug level.** `botocore` logs the `ListFunctions` response, values included, when logging is at `DEBUG`.
- **A crash can hide a failed check.** After a crash at the evidence step, the retry saw no change, so VC-060 evidence stayed stale and the system dropped from `control_not_met` to `no_evidence` until the refresh, about three weeks later.
- **Same-day assessment misses the crawl.** `verity assess` defaults to the start of today, before the crawl's evidence was collected.

These fixes make no AWS changes.

## Decision
1. **AI actions are a concrete list.** `ai_actions` in `ai_signals.yaml` names real IAM actions, not patterns. A statement grants a listed action if it is `Allow` and either one of its `Action` patterns matches, or it is a `NotAction` statement and none of its patterns match. This replaces ADR 0021's rule that `NotAction` is ignored, so `unparsed` goes. A pattern such as `bedrock:*Model` now resolves too. VC-060 and the `iam_ai_action` signal both use this. `Deny` statements are still not subtracted, which errs towards reporting a grant.
2. **Each action names the CloudTrail events that prove it.** `bedrock:InvokeModel` is proved by `InvokeModel` and `Converse`, and `bedrock:InvokeModelWithResponseStream` by `InvokeModelWithResponseStream` and `ConverseStream`. **This corrects ADR 0007:** the seeded unused grant is `bedrock:InvokeModel`. The never-use policy already denies `bedrock:Invoke*`, so nothing can invoke it. Only `AwsApiCall` events count: a stream-completion event is not a call.
3. **VC-060 has a third outcome, `inconclusive`.** In order: `fail` if a granted action with listed events has none for that role; `inconclusive` if a granted action has no listed events, so history cannot show it, or if a function of the system has a role the crawler cannot see; otherwise `pass`. The assessor already acts only on `fail` and `pass`, so `inconclusive` gives Not assessed and a `no_evidence` finding. The latest result still wins, so it replaces an older pass. The content records `granted`, `unused`, `unverifiable` and `roles_unseen`.
4. **A 12-digit number becomes a digest, not a placeholder.** `scrub` turns each one into `acct_<first 8 hex of its sha256>`, which is valid in an ID part, an env var name and an ARN. This replaces `<account>` from ADR 0021, decision 3. Different accounts stay different, so a trust change gives a ChangeEvent. Different numbers in names stay different, and no name stops a run. A table ARN takes its account digest from the collected role ARNs, because `ListTables` gives names only.
5. **Env var names and resource names match anywhere.** The env pattern matches a vendor word as a whole `_`-separated part, in any position. The name tokeniser also splits CamelCase. `invoice-renderer`, `mail-sender` and `maintenance-job` must still score *none*.
6. **The crawler silences AWS library logs.** `AwsCollector.collect` sets the `botocore`, `boto3` and `urllib3` loggers to `WARNING` before any call, so D1 holds whatever the root level is.
7. **Stale evidence is written again.** A resource's snapshot or a system's VC-060 Evidence is also written when the latest one is stale from a stored ChangeEvent. This makes ADR 0021's "repaired by the next run" true.
8. **The platform exemption needs a reviewed name.** A function is exempt only if it holds `platform_tag` **and** its name is in `platform_functions` in `ai_signals.yaml`. The tag alone does nothing. This narrows ADR 0021, decision 15.
9. **`verity assess` means now by default.** With no `--as-of`, or with today's date, `as_of` is the current time. Any other date is still the start of that day.
10. **Smaller changes.** A manifest naming a function that does not exist is counted in `summary.manifest_functions_missing` and reported, and is not a finding.
11. **Recorded from the M6 build.** These were built differently from ADR 0021 and are confirmed:
    - The content field is `control: ctl:VC-060`, the full ID the assessor matches on.
    - An unlinked function scoring *confirmed_usage* also becomes a Candidate, and its `shadow_ai_candidate` is high.
    - A promoted Candidate that qualifies again has its `PROMOTED_TO` edge closed, so the finding returns.
    - VC-060 Evidence is also written when a source changed, or the set of sources did.

## Alternatives
| Option | Why not chosen |
|---|---|
| Treat `NotAction` as `inconclusive` | With a concrete list the grant can be worked out exactly, and `PowerUserAccess` then fails, which is the true answer |
| Keep patterns in `ai_actions` | Comparing two patterns misses `bedrock:*Model`, and a pattern cannot carry which events prove it |
| Treat an action with no events as unused | SageMaker and agent calls would always fail on a gap in our sources, not in the role |
| Treat an unseen role as a pass on what was seen | The result would claim more than was checked |
| Hash the raw config, with account IDs | Works for detection only, and leaves `<account>` breaking names |
| Replace only the ARN account field | An account ID inside a role name, as CDK writes, would stay in the data |
| Salt the digest | There is no safe place for the salt in the crawler, and M9 can replace digests on export |
| Remove the platform exemption | `mock-openai` would be a permanent false candidate |
| Keep `as_of` at the start of the day and run assess the next day | A person reading results after a crawl would see them disappear |

## Consequences
- A broad role now fails VC-060. An admin role on an AI system is a real finding.
- A grant of `bedrock:*` fails while any covered action with listed events is unused, even if `InvokeModel` is used. That is what the control asks.
- `inconclusive` shows as `no_evidence`, so its reason is in the Evidence and not the finding.
- **An `acct_` digest is not anonymous.** Twelve digits can be searched, and 8 hex narrows an account to a few hundred candidates. M9 replaces digests with ordinals on export.
- The real `verity-crawler` function name must match `platform_functions`. M8 confirms it.
- The list of AI actions needs checking against the IAM reference before M8, because that page could not be read here.
