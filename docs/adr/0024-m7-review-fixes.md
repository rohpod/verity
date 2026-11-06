# 0024 — M7 review fixes: bounded telemetry, quiet logs, a usage partition and reproducible zips
- **Status:** Accepted (2026-11-06). Refines [0023](0023-m7-demo-estate.md), [0013](0013-dynamodb-write-model.md) and [0022](0022-m6-review-fixes.md); all stay in force, except where *Decision* 3 changes 0013's key table, *Decision* 1 and 4 make 0023's decisions 7 and 12 true, and *Decision* 9 corrects 0022.

## Context
The end-of-milestone review of M7 passed the validation criteria, then ran the real zips' handlers against a local fake of DynamoDB, Lambda and the Function URL, with fake credentials. It reproduced cases where the estate breaks a decision or a promise. Nothing reached AWS.
- **Telemetry can fail the call.** ADR 0023 says it never does. The usage sink uses the client built for graph writes, with 10 attempts and default timeouts. A throttled write held the handler for 37.1 seconds, and the functions have a 10-second timeout, so Lambda would kill the call. This is likely while `verity assess --target dynamodb` uses the table's full write capacity.
- **`LOG_LEVEL=DEBUG` logs secrets.** The apps set the root logger's level, so botocore logs too. The customer's message and the session token both appeared in `support-assistant` logs, and the session token in `contract-insights` logs. The docstring says the message is never logged. M6 fixed the same problem for the crawler in [ADR 0022](0022-m6-review-fixes.md). The tests missed it because they use fakes, so botocore never ran.
- **An app role can rewrite its own system.** Usage records share a partition with the system's `META`, edge and history items. `dynamodb:LeadingKeys` limits the partition key only, and IAM has no matching condition for a sort key. D8's limit therefore does not stop `dynamodb:PutItem` replacing the `AISystem` record. This comes from how IAM works and was not tested.
- **Zips are not reproducible.** The build ships every file in a source folder, so `.DS_Store` or `.env` goes in. Only `pydantic` is pinned, so a new release of a dependency changes `CodeSha256` with no change of ours.
- **All of `verity_core` ships in two zips,** and 32 of its 59 files are never imported there. An edit to `assess` would raise a ChangeEvent on two functions it cannot affect.
- **Talent Screening takes impossible input.** An applicant with `skills_match: 50` and `years_experience: -40` ranked first with a score of 1.0.
- **A redirect escapes the endpoint guard.** A 302 from the Function URL sent the `Authorization` and session token headers to a second host.
- **`mock-openai` crashes on some bad input,** and accepts a request with no `model`.
- **The no-real-provider test has gaps.** `'bed' + 'rock-runtime'` passes in `discovery/aws.py`, and so does `boto3.resource('bedrock-data-automation-runtime')`.
- **ADR 0022 is wrong that nothing can invoke Bedrock.** `verity-never-use` is an inline policy on the user `rohpod` ([ADR 0015](0015-account-baseline.md)), so it does not cover a Lambda role. `support-assistant`'s role will really hold `bedrock:InvokeModel`, and only code stands between it and a call paid from credits.

The fixes make no AWS changes. No app is deployed, so no real usage record exists yet.

## Decision
1. **Telemetry has a time budget.** `client.py` gains `usage_client()`: 2 total attempts, 0.5 s to connect and 1 s to read, so a write gives up within about 4 seconds. `DynamoDBUsageSink` uses it by default. `DynamoDBRepository` still passes its own client, so graph writes keep their retries. The adapter's `TIMEOUT` falls from 8 to 5 seconds. `lambda_invoker` gets short timeouts and 1 attempt, because a retried model call counts twice. The model and telemetry budgets together stay under the 10-second function timeout, and a test pins that sum against the fixture. A throttled write loses that usage record, which decision 7 of ADR 0023 already accepts.
2. **Apps never touch the root logger.** `LOG_LEVEL` sets the app's own named logger and `verity_ai`'s. `verity_ai.aws` also sets `botocore`, `boto3` and `urllib3` to `WARNING` before creating a client or signing, as `AwsCollector` does, so the promise holds whatever the root level is. That includes Lambda's own log-level setting.
3. **Usage records get their own partition.** The PK becomes `T#{tenant}#U#{system}`, and the SK stays `U#{iso_ts}#{usage_id}`. An app role's `LeadingKeys` condition then names a partition holding only that system's usage. The worst an app can do is damage its own usage records, which are simulated and never the only proof of anything. **This changes ADR 0013's key table.** Reads change only in `usage_records`. The scan in `load_graph` still sees and discards them. Conditions use `ForAllValues:StringEquals`, not `StringLike`, because the key holds no wildcard.
4. **Zips hold tracked files at locked versions.** The build takes source files from `git ls-files`, so an untracked file cannot ship. Uncommitted edits to tracked files still do, so build from a clean tree before deploying. Vendoring installs `pydantic` and everything it depends on in `uv.lock`, each at its locked version, with `--no-deps`. This makes decision 12 of ADR 0023 hold over time.
5. **The two zips carry only the `verity_core` they import:** `model/`, `graph/errors.py`, `graph/planning.py`, the `__init__.py` files on the way, and `client`, `items`, `keys`, `table` and `usage` in `graph/dynamodb/`. A test runs the handlers from the built zip, so a missing file fails. An edit to one of these files does change the hash, which is correct: the deployed code changed.
6. **Impossible input is refused, and unusual input is flagged, not refused.** `coefficients.json` gains two tables from `train.py`:
   - `valid_ranges`: what can exist. `skills_match` 0 to 1, `assessment_score` 0 to 100, and `years_experience`, `certifications` and `relevant_projects` 0 to 60. Outside these the request is refused, and the error names the feature, never the value.
   - `training_ranges`: what the model saw. Outside these the applicant is still ranked, with `outside_training_range` listing the features, so the recruiter can see the score is an extrapolation.

   Refusing on the training range would turn away anyone with over 20 years' experience. That would be an age proxy in a system whose named risk is bias. The coefficients do not change, so `model_version` stays.
7. **Adapters fail one way.** `urllib_transport` follows no redirects, so a 3xx becomes `AdapterError` and the guard of ADR 0023, decision 8 holds for every request. A connection error, a timeout, a body that is not JSON or a response missing `usage` also becomes `AdapterError`. A Lambda client error does too.
8. **Smaller changes.**
   - `mock-openai` answers 400 for any bad input, including a missing `model`.
   - `support-assistant` returns `simulated: true`, as the other two do.
   - The provider test treats any string starting `bedrock-` or `sagemaker-` as a real service, covers `.resource(` and `create_client(`, and checks for dynamic service names in all three files allowed to use boto3. `AwsClients.create` therefore names its services as constants.
   - A zip test requires `cpython-312` in compiled file names.
   - The review's handler experiments become repository tests, on a local fake with real botocore, so these failures cannot return unseen.
9. **M8 puts a permissions boundary on the app roles.** It allows everything except `bedrock:Converse*`, `bedrock:Invoke*` and `sagemaker:InvokeEndpoint*`. **This corrects ADR 0022:** until then, nothing in AWS stops a real call. The grant stays in the role's policy, so the seeded VC-060 finding stands, because the crawler does not read boundaries. That finding then describes a grant the boundary makes ineffective, and the UI must say so. IAM has no charge, and M8's plan confirms the details and asks for approval first.

## Alternatives
| Option | Why not chosen |
|---|---|
| Keep usage in the node partition and accept the risk | No usage data exists yet, so this is the cheapest moment, and M8 writes the policy that depends on it |
| A separate usage table | 25 of 25 capacity units are in use |
| `dynamodb:Attributes` to limit what an app writes | It limits attributes, not which item, so `PK`, `SK` and `doc` would all have to be allowed |
| Write telemetry on a background thread | Lambda freezes the process after the response, so the write may never finish |
| Refuse input outside the training range | Refuses long-serving applicants: an age proxy |
| Clip input to the training range | Changes the score without saying so |
| Build from `git archive` of a commit | Stricter, but it needs a commit before every local build. Tracked files give the property that matters |
| Attach `verity-never-use` to the role | It would work, but a boundary also caps what a later edit to the role's policy can grant |

## Consequences
- Telemetry undercounts more readily, because it now gives up after two tries. The log line stays the only sign.
- Reading a system's usage no longer needs its node partition. Anything that assumed `node_pk` for usage must move to `usage_pk`.
- `usage_records` would not see a `U#` item left under an `N#` key. No app has written one.
- The app's `LOG_LEVEL` no longer shows AWS library logs. Debugging those needs a local run.
- `coefficients.json` gains fields, so a retrain must reproduce them. `golden.json` does not change.
- **Still unverified:** the SigV4 signing name `lambda`. The Function URL invocation page does not state it, so M8 proves it live. The OpenAI response shape stays from knowledge.
- **Not tested:** that `LeadingKeys` and the boundary behave as described on real IAM. M8 proves both with a refused write and a refused invoke.
