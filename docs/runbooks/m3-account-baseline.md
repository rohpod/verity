# Runbook: M3 account baseline

Owner steps for [ADR 0015](../adr/0015-account-baseline.md). Console labels change, so follow the intent if a name differs. Never paste an account ID, email or credential into the repo.

## 1. Grant access (once, as root)
1. Sign in as root and confirm MFA is on: **IAM → Dashboard → Security recommendations**.
2. **IAM → Users → rohpod → Security credentials → Assign MFA device.**
3. **Permissions → Add permissions → Attach policies directly → `AdministratorAccess`.**
4. **Permissions → Add permissions → Create inline policy → JSON.** Paste `infra/bootstrap/verity-never-use.json` and name it `verity-never-use`.
5. **Billing and Cost Management → Billing preferences:** turn on Free Tier usage alerts.
6. Note the remaining credits and the plan end date. Compare them after any live work.
7. Sign out of root.

## 2. Sign in and set up the profile (local)
Run `aws login`, and note whether it asks for your MFA code. Then add this to `~/.aws/config`:

```ini
[profile verity]
region = eu-north-1
credential_process = aws configure export-credentials --profile default --format process
```

Use it with `export AWS_PROFILE=verity`. A session lasts up to 12 hours, then run `aws login` again.

If `aws` is not found when the profile runs, use the full path from `which aws`.

## 3. Configure OpenTofu (local)
```sh
cd infra
cp terraform.tfvars.example terraform.tfvars   # git-ignored: add your account ID and email
tofu init
tofu plan
```

## Never run
`aws ce ...`: Cost Explorer charges $0.01 per request. Read credits in the Billing console.

## Delete everything
1. `cd infra && tofu destroy` removes the table, its data and the budget.
2. Remove the permissions from `rohpod` as root, if you want to undo step 1.

## If local state is lost
The resources still exist. Rebuild the state:

```sh
tofu import module.table.aws_dynamodb_table.graph verity-graph
tofu import module.guardrails.aws_budgets_budget.zero_spend <account-id>:verity-zero-spend
tofu plan   # should report no changes
```
