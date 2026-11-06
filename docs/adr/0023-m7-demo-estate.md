# 0023 — M7 demo estate: layered adapters, a corrected fixture, a real local model and deterministic zips
- **Status:** Accepted (2026-11-06). Refines [0007](0007-mock-only-ai-providers.md), [0009](0009-mock-openai-iam-auth.md) and [0021](0021-m6-discovery.md); all stay in force, except where *Decision* 8 amends 0007.

## Context
M6 proved the crawler against a recorded fixture. M8 will deploy a real estate for it to crawl, but that estate has no code yet: `sdk/`, `apps/` and `mocks/` do not exist. M7 writes it. Reading the fixture against the project rules showed it describes an estate that cannot exist:
- **A second table is impossible.** `HELP_ARTICLES_TABLE` needs a table, and `verity-graph` already uses all 25 free capacity units.
- **S3 is banned.** `TEMPLATE_BUCKET` names a bucket.
- **App roles never read (D8).** `support-assistant` holds `dynamodb:GetItem` on `verity-graph`.
- **`mock-bedrock` is missing,** though `support-assistant` is meant to call it.
- **Two things are open.** Where a function pays for `verity_core`, and how `CodeSha256` behaves, because it feeds `config_hash`.

M7 makes no AWS calls. AWS paths are tested with `moto` or fakes, and M8 deploys.

## Decision
1. **`verity_ai` is layered so a function pays only for what it uses.** `verity_ai/__init__.py` imports nothing heavy. `bedrock.py` and `openai.py` are stdlib only. `telemetry.py` is the only module that imports `verity_core`. `aws.py` is the only one that imports boto3 or botocore.
2. **`sdk/verity_ai/aws.py` is the third file allowed to use boto3.** It holds the Lambda invoker and the SigV4 signer. The adapters take these as injected callables, and app code never imports boto3. `DynamoDBUsageSink` stays in `verity_core`, so D8 and "graph access through the graph package" stand. The boundary test allows exactly that one file more.
3. **The fixture is corrected, because it broke rules M7 must keep.**
   - `HELP_ARTICLES_TABLE` becomes `HELP_ARTICLES_FILE`. Articles ship in the zip.
   - `TEMPLATE_BUCKET` becomes `INVOICE_TEMPLATE`. The template ships in the zip.
   - `dynamodb:GetItem` on `verity-graph` becomes `dynamodb:PutItem` with a `dynamodb:LeadingKeys` condition.
   - `mock-bedrock` is added, shaped like `mock-openai`.
   - Roles gain the grants the code needs: `lambda:InvokeFunction` on `mock-bedrock` for `support-assistant`, and `lambda:InvokeFunctionUrl` plus `lambda:InvokeFunction` on `mock-openai` for `contract-insights` and `shadow-summariser`. A Function URL needs both ([urls-auth](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html), read 2026-11-06).
   - `support-assistant` keeps `bedrock:InvokeModel`, the seeded finding of ADR 0022.
4. **`usage` is a required keyword on both adapters, and `None` is a deliberate choice.** Forgetting telemetry is then impossible. Only `shadow-summariser` passes `None`.
5. **`shadow-summariser` really calls mock-openai, without telemetry and without `verity_core`.** It uses `OpenAICompatible` with `usage=None`: a team that wired up the client and never registered the system. It has a role grant, which gives a real `CALLS` edge, and no `U#` records. It stays *probable* and a Candidate. A usage record could not exist anyway, because it has no system ID.
6. **Talent Screening writes no usage records.** `UsageRecord.provider_id` is required and an in-house model has no provider, and the role stays logs-only. Usage records are therefore evidence of third-party model calls only.
7. **Usage telemetry never fails the call.** It is written after a successful response only. A failed write is logged as `usage_write_failed` with the exception type and no content, and the call still returns. A telemetry outage therefore undercounts usage. Usage records are never the only proof of anything, and VC-060 ignores them.
8. **Adapters refuse real endpoints at runtime, not just by convention.** `OpenAICompatible` accepts only `https://*.lambda-url.eu-north-1.on.aws` or `http://localhost`. `lambda_invoker` accepts only function names starting `mock-`. **This amends ADR 0007:** swapping in a real provider is no longer "changing configuration, not code". It is a deliberate code change.
9. **Simulation is labelled inside the valid shape.** Converse refuses unknown top-level fields (probed on botocore 1.43.124), so mock-bedrock sets `additionalModelResponseFields: {"simulated": true}`. mock-openai sets `system_fingerprint: "verity-mock"` and the header `x-verity-simulated: true`. Both start reply text with `[SIMULATED]`. Model IDs are invented (`mock.bedrock-fm-v1`, `mock-gpt-class`), never real ones. `UsageRecord.source` is `Source.SIMULATED`.
10. **Training uses scikit-learn in a separate `train` dependency group, and the Lambda uses none of it.** Inference is hand-written pure Python, so comparing the two tests two independent implementations. `training/golden.json` holds held-out inputs with scikit-learn's probabilities, and the always-on test compares against it with a tolerance of `1e-9`. A retrain test uses `pytest.importorskip` and runs locally, because retraining in CI could flake across platforms.
11. **The model has no protected attributes, and this milestone adds no bias test.** The input schema refuses unknown fields, so `gender` or `name` cannot reach it. VC-014's gap is a seeded finding and stays.
12. **Zips are deterministic.** `CodeSha256` feeds `config_hash`, so a zip that changed on every build would raise a false ChangeEvent and make evidence stale on each apply. Entries are sorted, timestamps and modes fixed, and there is no `__pycache__` or `*.dist-info`.
13. **Only `pydantic` is vendored.** Importing `verity_core.graph.dynamodb.usage` loads pydantic and boto3 but not `networkx` or `yaml` (probed). boto3 comes from the Lambda runtime and is never vendored. The `core` package with all its dependencies for arm64 zips to 5.7 MB, so this lands lower.
14. **Each function is one `app.py` with `handler = app.handler`,** matching the fixture. There are no sibling modules, so the shared name `app` cannot collide. Tests load each by path.

## Alternatives
| Option | Why not chosen |
|---|---|
| One `verity_ai` module importing everything | `invoice-renderer` and `shadow-summariser` would carry pydantic for nothing, and `shadow-summariser` could not honestly lack `verity_core` |
| A second DynamoDB table for articles | 25 of 25 capacity units are in use |
| Bundle the template and articles through S3 | S3 is banned |
| Let apps read the graph table | Breaks D8: app roles never read |
| Usage records for Talent Screening | `provider_id` is required and an in-house model has no provider |
| Fail the call when telemetry fails | A governance side-channel would take the product down |
| Train in CI | Cross-platform float differences could make the test flake |
| Use scikit-learn at inference | Heavy for a Lambda, and the test would compare a library with itself |
| Vendor all of `verity_core` | Pulls `networkx` and `yaml` into two zips |

## Consequences
- Usage records are evidence of third-party model calls only. An in-house model leaves no `U#` record, and VC-060 never reads them.
- A telemetry outage undercounts usage, and says so only in a log line.
- Moving to a real provider needs code changes in the adapters' guards, by design.
- **Unverified:** the OpenAI chat-completion response shape. The API reference returned 403 to automated fetches on 2026-11-06, twice, so the mock follows knowledge, not a re-read. The test is a hand-written shape assertion, not a schema check.
- **Unverified:** the SigV4 signing name `lambda` for a Function URL. No page read here confirms it, and M8 proves it live.
- M8 grants both Function URL actions, writes the `LeadingKeys` policy for `T#kestrel#N#sys:<system>`, tags both mocks `verity:component`, publishes the manifests, and takes env values from the names in the parity test.
