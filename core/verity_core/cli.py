"""The `verity` command (architecture section I). M4 adds `lint` and `seed`."""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from verity_core.content.lint import lint
from verity_core.content.loader import Content, ContentError, load_content
from verity_core.content.seed import SeedEstimate, estimate, seed
from verity_core.graph.memory import InMemoryRepository

OK, LINT_FAILED, UNREADABLE, REFUSED = 0, 1, 2, 3
PROGRESS_EVERY = 25


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _print_progress(what: str, done: int, total: int) -> None:
    if done % PROGRESS_EVERY == 0 or done == total:
        print(f"  {what}: {done}/{total}", file=sys.stderr, flush=True)


def _describe(plan: SeedEstimate) -> str:
    return (
        f"{plan.nodes} nodes and {plan.edges} edges: about {plan.table_units} write units on the "
        f"table and {plan.index_units} on the index, roughly {plan.seconds / 60:.1f} minutes at "
        "the provisioned capacity for a first seed. A re-seed writes almost nothing."
    )


def _load_and_lint(root: Path, tenant: str) -> Content | int:
    """The content if it is readable and lints clean; otherwise the exit code to return."""
    try:
        content = load_content(root, tenant=tenant)
    except ContentError as exc:
        print(f"cannot read content: {exc}", file=sys.stderr)
        return UNREADABLE
    issues = lint(content)
    for issue in issues:
        print(f"{issue.code}  {issue.subject}  {issue.message}", file=sys.stderr)
    if issues:
        print(f"{len(issues)} lint issue(s)", file=sys.stderr)
        return LINT_FAILED
    return content


def cmd_lint(args: argparse.Namespace) -> int:
    loaded = _load_and_lint(args.content, args.tenant)
    if isinstance(loaded, int):
        return loaded
    print(f"content passes lint: {len(loaded.nodes())} nodes, {len(loaded.edges)} edges")
    return OK


def cmd_seed(args: argparse.Namespace) -> int:
    loaded = _load_and_lint(args.content, args.tenant)
    if isinstance(loaded, int):
        return loaded
    plan = estimate(loaded)
    print(_describe(plan))

    if args.target == "memory":
        # A dry run that is real: it checks every edge against its endpoints.
        repo = InMemoryRepository(args.tenant, _utc_now)
        seed(repo, loaded, _utc_now)
        print("dry run only: nothing was written to AWS. Use --target dynamodb to seed the table.")
        return OK

    if not (args.yes or _confirmed()):
        print("not confirmed: nothing was written", file=sys.stderr)
        return REFUSED
    # Imported here so a dry run needs no AWS libraries.
    from verity_core.graph.dynamodb.repository import DynamoDBRepository

    repo = DynamoDBRepository(args.tenant, _utc_now)
    print("seeding the real table, expect pauses while it throttles...", file=sys.stderr)
    report = seed(repo, loaded, _utc_now, _print_progress)
    print(
        f"nodes: {report.nodes_written} written, {report.nodes_unchanged} unchanged; "
        f"edges: {report.edges_written} written, {report.edges_unchanged} unchanged"
    )
    return OK


def _confirmed() -> bool:
    if not sys.stdin.isatty():
        return False
    answer = input("This writes to the real verity-graph table in eu-north-1. Type 'seed': ")
    return answer.strip() == "seed"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verity", description="Verity AI governance platform")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler: Callable[[argparse.Namespace], int], help_text: str):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--content", type=Path, default=Path("content"), help="content directory")
        sub.add_argument("--tenant", default="kestrel")
        sub.set_defaults(handler=handler)
        return sub

    add("lint", cmd_lint, "check the content files")
    seed_parser = add("seed", cmd_seed, "load the content into the graph")
    seed_parser.add_argument(
        "--target",
        choices=("memory", "dynamodb"),
        default="memory",
        help="memory is a dry run (default); dynamodb writes to the real table",
    )
    seed_parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


def main() -> None:
    sys.exit(run())
