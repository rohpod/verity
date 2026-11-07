# Runbook: M8 deploy and first live crawl

The live steps of [ADR 0025](../adr/0025-m8-deploy-and-crawl.md). This changes the real account, so **every step marked APPROVE needs the owner's yes for that step, at that moment**, with what it creates, the verified price and how to undo it. Approval of one step never covers the next. Stop at the first surprise and record every measured value as you go.

Run everything with `export AWS_PROFILE=verity`. Never paste an account ID, ARN, Function URL or email into the repo, a PR or an ADR. Never make a Bedrock or SageMaker call, even one expected to be refused: Bedrock and OpenAI stay mock-only.

Prices (read 2026-11-06, ADR 0025): Lambda, including Function URLs, is inside the Always Free allowance; EventBridge Scheduler has 14,000,000 free invocations a month; SSM Standard parameters, IAM and the permissions boundary have no charge; log groups with 3-day retention stay far inside 5 GB.

| # | Step | Command or action | Expected | Undo |
|---|---|---|---|---|
| L0 | **Owner** reads credits in the Billing console | Not `aws ce`: Cost Explorer charges per request | Baseline recorded | n/a |
| L1 | Clean tree, current `main`, build | `git status`, `git pull --ff-only`, `uv run python scripts/build_lambdas.py`, `shasum -a 256 .build/*.zip` | Empty `git status`. Record each zip's SHA-256 | n/a |
| L2 | APPROVE: seed the graph | `uv run verity seed --target dynamodb` | Time it (measured 649 s on 2026-11-06, slowed by credential refreshes: ADR 0028). Do not run a second seed | `tofu destroy` removes the table and its data |
| L3 | Plan, shown to the owner in full | `cd infra && tofu plan -var enable_probe=true` | Only approved types. Nothing changes in `module.table` or `module.guardrails`. No table replacement | n/a |
| L4 | APPROVE: create the estate | `tofu apply -var enable_probe=true` (schedule stays `DISABLED`) | All resources created | `tofu destroy -target=module.estate` |
| L5 | APPROVE: invoke each of the 5 apps once | `aws lambda invoke --function-name <name> --cli-binary-format raw-in-base64-out --payload file://event.json out.json` with the events in `tests/build/test_zip_handlers.py` | All return. Exactly 2 usage items under `T#kestrel#U#`. Proves the arm64 `pydantic_core` and the SigV4 signing name `lambda` | n/a (2 small items) |
| L6 | Read each `REPORT` line | `aws logs tail /aws/lambda/<name> --since 15m` | Duration and Init Duration recorded. `support-assistant` or `contract-insights` over 3 s in the handler: stop (ADR 0026) | n/a |
| L7 | Unsigned `curl` to the Function URL | Read the URL with `aws lambda get-function-url-config --function-name mock-openai`, never print or commit it | 403, and the function did not run | n/a |
| L8 | APPROVE: invoke `verity-probe` | `aws lambda invoke --function-name verity-probe out.json` | `AccessDeniedException` twice. `ConditionalCheckFailedException` means IAM allowed the write: stop | n/a (nothing is written) |
| L9 | APPROVE: simulate the boundary | `aws iam simulate-principal-policy --policy-source-arn <support-assistant-role> --action-names bedrock:InvokeModel`, then again with `--permissions-boundary-policy-input-list` set to an allow-all policy | Deny from the boundary (`PermissionsBoundaryDecisionDetail`), then allow with the control. The simulator calls no Bedrock API | n/a |
| L10 | APPROVE: remove the probe | `tofu apply -var enable_probe=false` | Probe gone before any crawl | n/a |
| L11 | APPROVE: first crawl | `uv run verity crawl` | Classifications below | n/a |
| L12 | APPROVE: assess | `uv run verity assess --target dynamodb` | 29 high findings, or stop. Time it (measured 41 min on 2026-11-06, slowed by credential refreshes: ADR 0028) | n/a |
| L13 | APPROVE: second crawl | `uv run verity crawl` | Writes only the run. Record `largest_evidence_bytes` and the scan's time | n/a |
| L14 | Check CloudTrail | `aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventSource,AttributeValue=bedrock.amazonaws.com` | No `Invoke*` or `Converse*` events. Resource Explorer's own `List*` calls appear (7, dated 2026-11-05) and are not use (ADR 0027, ADR 0028) | n/a |
| L15 | APPROVE: enable the schedule | `tofu apply -var schedule_state=ENABLED` | Next day: one run, `finished_at` set. Run this after L16 and leave it `ENABLED`: a plain `tofu apply` sets it back to `DISABLED` (ADR 0028) | Apply with `DISABLED` |
| L16 | APPROVE each: rebuild test | `tofu destroy -target=module.estate`, then `tofu apply`, then a crawl | Table and budget untouched. Same zip hashes. High findings hold | n/a |
| L17 | **Owner** reads credits at least 24 hours after the latest one-off change (the 07:30 UTC run, the cron revert and B4), so at or after 10:12 UTC on 2026-11-08. Daily crawls do not restart the wait (ADR 0032, decision 3) | Billing console | Unchanged | n/a |

## Expected classifications (L11)
Taken from `verity crawl --local`.

| Function | Likelihood | Linked by |
|---|---|---|
| `support-assistant` | declared | `ai:system-id` tag |
| `contract-insights` | declared | tag and manifest |
| `talent-screening` | declared | manifest |
| `shadow-summariser` | probable, Candidate | nothing |
| `invoice-renderer` | none | nothing |
| `mock-bedrock`, `mock-openai`, `verity-crawler` | none, `platform_component` | tag |

VC-060 fails on `support-assistant`, with `bedrock:InvokeModel` unused.

## Stop and switch to Opus
Stop and tell the owner to switch to Opus if: a high-finding count or any classification differs; `tofu plan` touches `module.table` or `module.guardrails` or holds an unapproved type; an apply is refused because of the Free plan; the simulator shows no deny from the boundary or the control does not allow; the probe returns anything but `AccessDeniedException`; the SigV4 signing name fails; a cold call to `support-assistant` or `contract-insights` takes over 3 seconds in the handler; the crawl needs an IAM action outside architecture §D; a crawl takes over 120 seconds; anything suggests a charge or credits move; or the same bug defeats two fixes.

## Notes
- `verity-probe` has no log group: it runs on `support-assistant-role`, which may only write to that function's own group. Its result is the invoke response.
- Build from a clean tree. The build takes tracked files, so an uncommitted edit to one still ships.
- Only one writer at a time (ADR 0014): never run a seed and a crawl together, and leave the schedule `DISABLED` until L15.
