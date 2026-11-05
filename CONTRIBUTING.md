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

### Local checks

Run these from the repository root. CI runs the same commands, so a green local run should mean a green PR. You need [`uv`](https://docs.astral.sh/uv/), which installs Python 3.12 for you.

```
uv sync                        # create .venv and install locked dependencies
uv run ruff check .            # lint
uv run ruff format --check .   # formatting (run `uv run ruff format .` to fix)
uv run pytest                  # tests
```

### Claude Code guardrail

`.claude/settings.json` registers a hook (`.claude/hooks/confirm-mutating-aws.py`) that makes Claude Code ask for confirmation before `tofu`/`terraform` `apply`, `destroy`, `import` or state edits, and before any `aws` command that is not a known read-only call. It is tested in `tests/test_aws_hook.py`. It guards the AI tool only; it is not an AWS permission.

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
