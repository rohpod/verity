# Contributing to Verity

Verity is a learning and portfolio project built to enterprise standards. These rules apply to every change, including changes made with AI coding tools.

## Workflow

1. **`main` is protected.** Never commit to it directly.
2. Update `main`, then create one branch per feature or fix.
3. Keep each pull request to one concern. A milestone may span several PRs.
4. Run the checks locally before pushing.
5. Open a PR using the template. Only the maintainer merges to `main`, on GitHub.
6. After the merge, delete the branch and update your local `main`.

## Branch names

Use `<type>/<short-description>`, optionally with the milestone: `feat/m1-graph-repository`, `fix/crawler-pagination`, `docs/adr-0011`.

## Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<optional scope>): <summary>`

| Type | Use for |
|---|---|
| `feat` | New behaviour |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Tests only |
| `refactor` | Code change with no behaviour change |
| `chore` | Tooling, dependencies, repo housekeeping |
| `ci` | GitHub Actions |
| `infra` | OpenTofu changes |

Write the summary in the imperative mood, in lower case, under about 72 characters: `feat(graph): add in-memory repository`.

## Before opening a PR

- Tests are written alongside the code and pass.
- Linting and formatting pass.
- The milestone's validation criteria in [`docs/stage-4-milestones.md`](docs/stage-4-milestones.md) pass, if the PR completes one.
- Docs are updated. A significant decision gets a new ADR in [`docs/adr/`](docs/adr/).

The exact commands are added to this file in milestone M0.

## Project rules

The full rules are in [`CLAUDE.md`](CLAUDE.md). The ones reviewers check most closely:

- **Zero cost.** No paid or metered AWS service, and no new AWS service without verified pricing.
- **AWS changes need approval.** Each `tofu apply`, `tofu destroy` or mutating `aws` command is approved individually, with what it creates, its verified price and how to delete it.
- **Be honest about simulation.** Bedrock and OpenAI are mock-only. Label simulated components in code, docs and UI.
- **Synthetic data only.** No real personal data.
- **No secrets.** Never commit credentials, `.env` files, OpenTofu state or real AWS account IDs.
- **No ISO text.** Reference ISO clauses by ID with original summaries.

## License

By contributing, you agree that your contribution is licensed under the [MIT License](LICENSE).
