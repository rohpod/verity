"""The `verity` command (architecture section I). M4 adds `lint` and `seed`, M5 `assess` and
`attest`, M6 `crawl`."""

import argparse
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import yaml
from pydantic import ValidationError

from verity_core.assess.apply import (
    ApplyResult,
    UnknownSystemError,
    apply_assessment,
    estimate_apply,
)
from verity_core.assess.requirements import RequirementState
from verity_core.content.lint import lint
from verity_core.content.loader import Content, ContentError, load_content
from verity_core.content.schema import AttestationDecision
from verity_core.content.seed import (
    INDEX_UNITS_PER_NODE,
    TABLE_UNITS_PER_RECORD,
    SeedEstimate,
    estimate,
    seed,
)
from verity_core.discovery.boundary import BoundaryError
from verity_core.discovery.collectors import FixtureCollector
from verity_core.discovery.pipeline import CrawlReport, crawl
from verity_core.graph.memory import InMemoryRepository
from verity_core.model.enums import ImplementationStatus
from verity_core.rules.status import ApplicabilityStatus

OK, LINT_FAILED, UNREADABLE, REFUSED = 0, 1, 2, 3
PROGRESS_EVERY = 25
_SEVERITY = {"high": 0, "medium": 1, "low": 2}


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
    try:
        report = seed(repo, loaded, _utc_now, _print_progress)
    except ContentError as exc:
        print(f"refused, nothing was written: {exc}", file=sys.stderr)
        return REFUSED
    print(
        f"nodes: {report.nodes_written} written, {report.nodes_unchanged} unchanged; "
        f"edges: {report.edges_written} written, {report.edges_unchanged} unchanged"
    )
    return OK


def _confirmed(word: str = "seed") -> bool:
    if not sys.stdin.isatty():
        return False
    answer = input(f"This writes to the real verity-graph table in eu-north-1. Type '{word}': ")
    return answer.strip() == word


def _start_of(day: date) -> datetime:
    return datetime.combine(day, time.min, UTC)


def _print_assessment(
    result: ApplyResult, as_of: datetime, *, verb: str, verbose: bool = False
) -> None:
    states = Counter(s.state for s in result.statuses)
    simulated = Counter(s.state for s in result.statuses if s.simulated)
    print(f"as of {as_of.date()}: {len(result.results)} control assessments")
    print(
        "requirements: "
        + ", ".join(
            f"{states[state]} {state.value}"
            + (f" ({simulated[state]} on simulated sign-offs)" if simulated[state] else "")
            for state in RequirementState
            if states[state]
        )
    )
    applicability = Counter(s.applicability for s in result.statuses if s.applicability)
    print(
        "applicability: "
        + ", ".join(
            f"{applicability[a]} {a.value}" for a in ApplicabilityStatus if applicability[a]
        )
    )
    findings = result.findings
    by_severity = Counter(f.severity.value for f in findings)
    print(
        f"{len(findings)} finding(s): "
        + ", ".join(f"{by_severity[s]} {s}" for s in _SEVERITY if by_severity[s])
    )
    # High findings are always listed. The rest are counted by code, unless --verbose lists them.
    shown = findings if verbose else [f for f in findings if f.severity.value == "high"]
    for finding in shown:
        line = f"{finding.severity.value:<6} {finding.code}  {finding.subject}"
        print(f"  {line}  {finding.message}")
    if not verbose:
        rest = Counter((f.severity.value, f.code) for f in findings if f.severity.value != "high")
        for (severity, code), n in sorted(
            rest.items(), key=lambda kv: (_SEVERITY[kv[0][0]], kv[0][1])
        ):
            print(f"  {severity:<6} {code}: {n}")
    written = ", ".join(f"{n} {kind}" for kind, n in sorted(result.written.items())) or "nothing"
    print(f"{verb}: {written}")


def cmd_assess(args: argparse.Namespace) -> int:
    loaded = _load_and_lint(args.content, args.tenant)
    if isinstance(loaded, int):
        return loaded
    if loaded.rules is None:
        print("cannot assess: content/rules/applicability.yaml is missing", file=sys.stderr)
        return UNREADABLE
    today = _utc_now().date()
    as_of = _start_of(args.as_of or today)

    if args.target == "memory":
        # Seeds a fresh in-memory graph, then assesses it. Nothing reaches AWS.
        repo = InMemoryRepository(args.tenant, _utc_now)
        seed(repo, loaded, _utc_now)
        try:
            result = apply_assessment(
                repo, loaded.rules, loaded.dates, as_of, _utc_now, system_id=args.system
            )
        except UnknownSystemError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return REFUSED
        _print_assessment(result, as_of, verb="stored in memory", verbose=args.verbose)
        print(
            "dry run only: nothing was written to AWS. Use --target dynamodb to assess the table."
        )
        return OK

    if as_of.date() != today:
        print(
            "refused: the real table is only assessed as of today, so a past or future date "
            "cannot overwrite the stored assessments",
            file=sys.stderr,
        )
        return REFUSED
    # Imported here so a dry run needs no AWS libraries.
    from verity_core.graph.dynamodb.repository import DynamoDBRepository

    repo = DynamoDBRepository(args.tenant, _utc_now)
    graph = repo.load_graph()
    if not graph.nodes:
        print("the table is empty: run `verity seed --target dynamodb` first", file=sys.stderr)
        return REFUSED
    try:
        plan = estimate_apply(
            graph, loaded.rules, loaded.dates, as_of, _utc_now, args.tenant, system_id=args.system
        )
    except UnknownSystemError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return REFUSED
    new_nodes = plan.written["assessments"]
    records = plan.total_written
    units = TABLE_UNITS_PER_RECORD * records + INDEX_UNITS_PER_NODE * new_nodes
    print(
        f"estimated writes: {records} records ({new_nodes} assessments), about {units} write units "
        "on the table. A second run writes nothing."
    )
    if not (args.yes or _confirmed("assess")):
        print("not confirmed: nothing was written", file=sys.stderr)
        return REFUSED
    result = apply_assessment(
        repo, loaded.rules, loaded.dates, as_of, _utc_now, system_id=args.system
    )
    _print_assessment(result, as_of, verb="written", verbose=args.verbose)
    return OK


def _print_crawl(report: CrawlReport, fixture: Path, *, verbose: bool) -> None:
    print(f"data source: recorded fixture {fixture}, simulated. Nothing was read from AWS.")
    print(f"{len(report.functions)} function(s) scored:")
    for name, likelihood, signals in report.functions:
        print(f"  {name:<20} {likelihood.value:<16} {', '.join(signals) or '-'}")
    print(f"{len(report.candidates)} candidate(s) for the registry:")
    for name, likelihood, signals in report.candidates:
        print(f"  {name:<20} {likelihood.value:<16} {', '.join(signals)}")
    if report.changes:
        print(f"{len(report.changes)} change(s): {', '.join(report.changes)}")
    if report.manifests_invalid:
        print(f"{report.manifests_invalid} manifest(s) were invalid and were skipped")
    written = ", ".join(f"{n} {kind}" for kind, n in sorted(report.written.items())) or "nothing"
    print(f"crawl wrote: {written}")
    if verbose:
        print("run summary: " + ", ".join(f"{k}={v}" for k, v in sorted(report.summary.items())))


def cmd_crawl(args: argparse.Namespace) -> int:
    """Crawls a recorded fixture into a fresh in-memory graph, then assesses it. Only `full`
    crawls exist, and the live path needs the deployed crawler (M8, ADR 0021)."""
    if not args.local:
        print(
            "refused: a live crawl needs the deployed crawler, which arrives in M8. Use --local "
            "to crawl the recorded fixture; it reads nothing from AWS.",
            file=sys.stderr,
        )
        return REFUSED
    loaded = _load_and_lint(args.content, args.tenant)
    if isinstance(loaded, int):
        return loaded
    if loaded.rules is None or loaded.signals is None:
        print(
            "cannot crawl: content/rules/applicability.yaml and ai_signals.yaml are needed",
            file=sys.stderr,
        )
        return UNREADABLE
    fixture = args.fixture or args.content / "fixtures" / "crawl" / "estate.json"
    repo = InMemoryRepository(args.tenant, _utc_now)
    seed(repo, loaded, _utc_now)
    try:
        report = crawl(repo, loaded, FixtureCollector(fixture), _utc_now)
    except (OSError, ValueError, BoundaryError) as exc:  # no raw record is ever in these
        print(f"cannot read the fixture {fixture}: {type(exc).__name__}", file=sys.stderr)
        return UNREADABLE
    _print_crawl(report, fixture, verbose=args.verbose)
    as_of = _utc_now()
    result = apply_assessment(repo, loaded.rules, loaded.dates, as_of, _utc_now)
    _print_assessment(result, as_of, verb="stored in memory", verbose=args.verbose)
    print("dry run only: nothing was written to AWS.")
    return OK


def cmd_attest(args: argparse.Namespace) -> int:
    """Scaffolds a decision file for review (D9). It never touches the graph."""
    today = _utc_now().date()
    slug = args.scope.partition(":")[2] or args.scope
    decision_id = f"attestation-{args.control.lower()}-{slug}"
    data = {
        "id": decision_id,
        "kind": "attestation",
        "decided_on": today,
        "by": args.by,
        "valid_until": today + timedelta(days=365),
        "simulated": True,  # a scaffold is a demo sign-off until the owner says otherwise
        "statement": (
            "Simulated sign-off by a fictional person. "
            f"TODO: say what {args.by} attests about {args.control} for {args.scope}."
        ),
        "control": args.control,
        "scope": args.scope,
        "status": args.status,
    }
    try:
        AttestationDecision.model_validate(data)
    except ValidationError as exc:
        print(f"cannot scaffold: {exc}", file=sys.stderr)
        return UNREADABLE
    path = args.content / "decisions" / f"{decision_id}.yaml"
    if path.exists():
        print(f"refused: {path} already exists", file=sys.stderr)
        return REFUSED
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print(f"wrote {path}")
    print(
        "Finish the statement, run `verity lint`, and open a pull request: the PR is the approval."
    )
    return OK


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

    assess_parser = add("assess", cmd_assess, "derive applicability and assess the controls")
    assess_parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="assess as of this date (default: today)",
    )
    assess_parser.add_argument("--system", metavar="ID", help="only this system, such as sys:x")
    assess_parser.add_argument(
        "--target",
        choices=("memory", "dynamodb"),
        default="memory",
        help="memory seeds, then assesses a fresh graph (default); dynamodb writes to the table",
    )
    assess_parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    assess_parser.add_argument("--verbose", action="store_true", help="list every finding")

    crawl_parser = add("crawl", cmd_crawl, "discover the AI estate and assess it")
    crawl_parser.add_argument(
        "--local",
        action="store_true",
        help="crawl a recorded fixture into a fresh in-memory graph; reads nothing from AWS",
    )
    crawl_parser.add_argument(
        "--fixture",
        type=Path,
        metavar="PATH",
        help="the recorded estate (default: <content>/fixtures/crawl/estate.json)",
    )
    crawl_parser.add_argument("--verbose", action="store_true", help="list every finding")

    attest_parser = add("attest", cmd_attest, "scaffold an attestation decision file")
    attest_parser.add_argument("control", help="control code, such as VC-001")
    attest_parser.add_argument("scope", help="the organisation, system or provider ID")
    attest_parser.add_argument("--by", required=True, help="person ID, such as person:l-ivanova")
    attest_parser.add_argument(
        "--status",
        choices=[s.value for s in ImplementationStatus][:3],
        default=ImplementationStatus.PARTIALLY_IMPLEMENTED.value,
        help="what is attested (default: partially_implemented)",
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
