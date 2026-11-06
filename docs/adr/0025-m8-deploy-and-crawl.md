# 0025 — M8 deploy and first live crawl: the crawler function, safe proofs and a fixture-shaped estate
- **Status:** Accepted (2026-11-06). Refines [0015](0015-account-baseline.md), [0021](0021-m6-discovery.md), [0023](0023-m7-demo-estate.md) and [0024](0024-m7-review-fixes.md); all stay in force, except where *Decision* 3 changes 0021's reading of CloudTrail, *Decision* 1 limits 0023's decision 13 and 0024's decision 5 to the app zips, and *Decision* 4 replaces 0024's "refused invoke".

## Context
M8 is the first milestone since M3 that changes the account, and the first time the estate runs at all. Planning it against the code raised these problems:
- **The prescribed Bedrock proof would destroy the seeded finding.** `_proves` and `trail_shows_ai` read an event's source and name, never its outcome. CloudTrail records failed calls with an `errorCode`, and Bedrock's `InvokeModel` and `Converse` are management events. A refused invoke from `support-assistant-role` would therefore count as use, VC-060 would pass, and the finding would vanish for the 90 days of event history. M8's own criterion, "CloudTrail shows no Bedrock use", would fail too. If the boundary were wrong, the same call could really run, against the mock-only rule.
- **`LeadingKeys` needs a real role.** App roles trust only `lambda.amazonaws.com`, and nothing in an app can attempt a write outside its partition.
- **The crawler has no package.** `pipeline.py` imports `networkx`, `yaml`, `assess.freshness` and `discovery`, so the rules for the app zips cannot apply to it. It needs only `signals` and `tenant` from `Content`.
- **Default tags would change the estate.** `default_tags` in `infra/main.tf` would put tags on `shadow-summariser`, which has none in the fixture and is meant to have none.
- **The schedule could collide with a seed.** Only one writer may run at a time ([ADR 0014](0014-m2-measurements-and-evidence-cap.md)).
- **"`tofu destroy` then apply" would delete the graph.**

## Prices and limits read for this decision (2026-11-06)
| Item | Finding | Source |
|---|---|---|
| Function URLs | No extra charge: "included in the regular cost of invoking Lambda functions". Closes the open finding | [What's New, 2022](https://aws.amazon.com/about-aws/whats-new/2022/04/aws-lambda-function-urls-built-in-https-endpoints/), [AWS blog](https://aws.amazon.com/blogs/aws/announcing-aws-lambda-function-urls-built-in-https-endpoints-for-single-function-microservices/) |
| Lambda | Always free on the Free and Paid plans: 1,000,000 requests and 400,000 GB-seconds a month | [Free compute](https://aws.amazon.com/free/compute/) |
| EventBridge Scheduler | 14,000,000 invocations a month free, then $1.00 a million | [Pricing](https://aws.amazon.com/eventbridge/pricing/) |
| SSM Standard parameters | No additional charge, including standard throughput | [Pricing](https://aws.amazon.com/systems-manager/pricing/) |
| Function URL auth | A same-account caller needs both `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction` in its identity policy, and no resource policy | [urls-auth](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html) |
| IAM simulator | "does not perform the API operations; it only checks the authorization". Results "can differ from your live AWS environment" | [API](https://docs.aws.amazon.com/IAM/latest/APIReference/API_SimulatePrincipalPolicy.html), [guide](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html) |
| AI action names | All 8 in `ai_signals.yaml` exist. `bedrock:Converse` is an operation, authorised by `InvokeModel`, not an IAM action. SageMaker has exactly the 3 listed | [Service Reference](https://servicereference.us-east-1.amazonaws.com/v1/bedrock/bedrock.json) |

The estate's use is far inside these allowances. The crawler at its limit of 256 MB for 300 s, once a day, is 2,250 GB-seconds a month, under 1% of the free amount.

## Decision
1. **The crawler is a function, `verity-crawler`, with its own zip.** `crawler/handler.py`, arm64, 256 MB, 300 s, `verity:component` tagged. It runs the crawl and never the assessment, which stays an operator command. Its zip has its own `verity_core` list, the 44 modules it imports, and vendors the locked closures of `pydantic`, `networkx` and `pyyaml`. It carries `rules/ai_signals.yaml` only, read by a new `load_signals`, so an edit to a framework does not change the crawler's hash. `networkx` and `yaml` stay out of every other zip.
2. **`verity crawl` without `--local` invokes the deployed function** and prints its summary. The handler returns counts only, never an ARN or a name. The invoke lives in `discovery/aws.py`, so the boto3 boundary does not move. The hook asks before this command.
3. **A CloudTrail event with an `errorCode` proves nothing.** `clean_trail_event` keeps the code, and `_proves` and `trail_shows_ai` ignore such events. A refused or failed call is not use of a grant. The code is kept as a value only, and the error message is dropped because it can hold request detail.
4. **The boundary is proved with the IAM simulator, never by attempting a Bedrock call.** `aws iam simulate-principal-policy` on `support-assistant-role` for `bedrock:InvokeModel` must give a deny, and the result's `PermissionsBoundaryDecisionDetail` must show the boundary as the reason. As a control, a simulation passing an allow-all boundary in `PermissionsBoundaryPolicyInputList` must give allow, so the deny is known to come from the boundary. **This replaces "a refused invoke" in ADR 0024.** No Bedrock request is ever sent, so none can be billed and CloudTrail stays clean. The cost is that this proves IAM's evaluation, not live enforcement, and the docs do not say outright that an attached boundary is included. The control covers that gap, and if the simulator cannot show the deny, the work stops.
5. **`LeadingKeys` is proved with a real refused write, from a temporary probe.** `verity-probe` runs on `support-assistant-role`, exists only while `enable_probe = true`, and is destroyed before the first crawl, so the crawler never sees it. It attempts `PutItem` on the system's `META` item and on another system's usage partition. Each write carries a condition that cannot be true, so if IAM wrongly allowed it the item would still be untouched, and the result would be `ConditionalCheckFailedException`, not `AccessDeniedException`. The DynamoDB call lives in `graph/dynamodb/`.
6. **The fixture is the estate's specification.** Tofu declares the seven functions as `content/fixtures/crawl/estate.json` describes them, and a test compares the two: names, memory, timeout, env names, tags and role policies. Estate resources use a provider alias without `default_tags`, so `shadow-summariser` and `talent-screening` really are untagged. Lambda roles are managed by OpenTofu. ADR 0015's rule that IAM identities stay outside it applies to people, not to function roles. Function URLs and ARNs are never outputs.
7. **Every function role carries the boundary `verity-function-boundary`.** It allows `*` and denies `bedrock:Converse*`, `bedrock:Invoke*` and `sagemaker:InvokeEndpoint*`, matching `verity-never-use`. `bedrock:Converse*` matches no action today and stays for safety. Log groups are created by OpenTofu with 3-day retention, and roles get no `logs:CreateLogGroup`, so a group can never appear without its retention.
8. **The schedule starts disabled.** It is enabled only after a manual crawl and a second one pass. It runs daily at 03:00 UTC with Scheduler retries off and `maximum_retry_attempts = 0` on the function, because a failed crawl is repaired by the next. Whether Scheduler invokes Lambda asynchronously could not be read, and setting both is harmless either way.
9. **The order is seed, deploy, probe, crawl, assess, schedule.** A crawl before a seed would find no systems to link to.
10. **The rebuild test destroys the estate only.** `verity-graph` and the budget stay. This also tests that the crawler ends and restores resources against a populated graph. The table's own rebuild was proved in M3.
11. **The AI action list stays as it is for M8.** Every name is real, which closes the open note. Bedrock has 8 further `Invoke*` actions, such as `InvokeDataAutomation`, that are not listed. No role here grants them, and whether event history shows them is unknown, so adding them is a separate content decision for after M8.
12. **Cold start is measured, not assumed.** If a healthy cold call to `support-assistant` or `contract-insights` takes over 3 seconds in the handler, memory moves to 256 MB for those two and the fixture changes with it. At these volumes that stays inside the allowance.
13. **Live results get their own ADR,** as M3's did ([ADR 0016](0016-m3-live-results.md)).

## Alternatives
| Option | Why not chosen |
|---|---|
| A real refused Bedrock call with a made-up model | Needs a Bedrock client, which the repository forbids, and leaves an AI event in CloudTrail for 90 days |
| A real refused call from `support-assistant-role` | Erases the seeded finding, and could run for real if the boundary were wrong |
| Prove `LeadingKeys` in the simulator as well | The simulator's pages do not mention that key, and this limit is cheap to test for real |
| Add `rohpod` to an app role's trust policy for the test | Changes the role's config, so the crawler would see it |
| Run the crawl locally with the operator's credentials | Never exercises the deployed role, which is the thing M8 must prove |
| Assess inside the crawler | About 5,900 write units on a first run, and it would pull the rules and the decisions into the zip |
| Ship all of `content/` in the crawler | A framework edit would raise a false ChangeEvent on the crawler |
| Keep `default_tags` on the estate | The fixture's untagged functions would be tagged, so live and local would differ |
| `tofu destroy` of everything | Deletes the graph and the crawl history, and forces a re-seed |

## Consequences
- VC-060 now reads a refused attempt as unused. A role that tries and fails stays a finding, which is right, but the attempt itself is not reported anywhere.
- The live estate has one more function and two more roles than the fixture, so resource counts differ from `verity crawl --local`. Classifications and high findings should not.
- The UI must say the boundary makes the `bedrock:InvokeModel` grant ineffective. That is M10's work.
- **Still unverified:** whether Free plan accounts may use EventBridge Scheduler, SSM and IAM. AWS's eligibility pages do not name them, and CLAUDE.md lists them as allowed. A refused apply costs nothing, and would stop the work.
- **Still unverified:** the default number of Lambda async retries, and how Scheduler invokes Lambda. Those pages could not be read.
- **Not proved by M8:** that the boundary blocks a real Bedrock call. The simulator's answer is the evidence, by the owner's choice.
