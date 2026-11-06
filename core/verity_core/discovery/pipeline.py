"""The crawl: collect, score, correlate, relate, diff, then persist (architecture section D,
ADR 0021). `crawl` reads the clock once, so `started_at`, `detected_at` and `collected_at` are
all the run's start and evidence of the same run is never stale. Everything before `persist` is
a pure function of the collected estate and the graph as it was.
"""

from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import networkx as nx

from verity_core.assess.freshness import stale_evidence_ids
from verity_core.content.loader import Content
from verity_core.content.schema import AiSignalsFile
from verity_core.discovery import CRAWLER_VERSION
from verity_core.discovery.boundary import CollectedRole
from verity_core.discovery.collectors import REGION, Collected, Collector
from verity_core.discovery.correlate import CandidateSpec, Link, candidates, in_manifest, links
from verity_core.discovery.diff import (
    config_hash,
    diff,
    expiring,
    function_config,
    role_config,
    table_config,
)
from verity_core.discovery.names import (
    LAMBDA,
    ROLE,
    TABLE,
    function_id,
    role_id,
    role_name_of,
    table_id,
)
from verity_core.discovery.persist import Plan, persist
from verity_core.discovery.relate import relations, role_of
from verity_core.discovery.signals import Score, score
from verity_core.discovery.usage import (
    CONTROL,
    check_vc060,
    granted_ai_actions,
    trail_shows_ai,
    usage_shows_ai,
)
from verity_core.graph.loader import node_record, out_edges
from verity_core.graph.repository import GraphRepository
from verity_core.model import ids
from verity_core.model.edges import Edge, PlainEdge
from verity_core.model.enums import (
    AiLikelihood,
    EdgeType,
    EvidenceKind,
    RunMode,
    Source,
)
from verity_core.model.evidence import INLINE_EVIDENCE_MAX_BYTES, Evidence, content_sha256
from verity_core.model.hashing import canonical_json
from verity_core.model.nodes import (
    AISystem,
    AWSResource,
    Candidate,
    ChangeEvent,
    DiscoveryRun,
)

CRAWLER_SOURCES = (Source.DISCOVERED, Source.SIMULATED)
RELATION_EDGES = (EdgeType.RUNS_ON, EdgeType.ASSUMES, EdgeType.CALLS)

Scored = tuple[str, AiLikelihood, tuple[str, ...]]  # a function's name, likelihood and signals


@dataclass(frozen=True)
class CrawlReport:
    run_id: str
    written: Counter[str]
    functions: tuple[Scored, ...]  # every function scored
    candidates: tuple[Scored, ...]  # the shadow-AI inbox
    changes: tuple[str, ...]  # IDs of the resources whose config changed
    manifests_invalid: int
    summary: dict[str, int]

    @property
    def total_written(self) -> int:
        return sum(self.written.values())


@dataclass(frozen=True)
class Built:
    functions: tuple[Scored, ...]
    candidates: tuple[Scored, ...]
    changes: tuple[str, ...]


def crawl(
    repo: GraphRepository,
    content: Content,
    collector: Collector,
    clock: Callable[[], datetime],
) -> CrawlReport:
    """One full crawl. `clock` must be the repository's own (see `persist`)."""
    if content.signals is None:
        raise ValueError("cannot crawl: content/rules/ai_signals.yaml is missing")
    started = clock()
    collected = collector.collect()
    graph = repo.load_graph()
    systems = [n for n in sorted(graph.nodes) if isinstance(node_record(graph, n), AISystem)]
    since = started - timedelta(days=content.signals.trail_lookback_days)
    usage = {s: usage_shows_ai(repo.usage_records(s, since=since)) for s in systems}
    plan, built = build_plan(
        graph, collected, content.signals, started, content.tenant, collector.source, usage
    )
    written, final = persist(repo, plan, clock)
    assert isinstance(final, DiscoveryRun)
    return CrawlReport(
        run_id=plan.run.id,
        written=written,
        functions=built.functions,
        candidates=built.candidates,
        changes=built.changes,
        manifests_invalid=collected.manifests_invalid,
        summary=dict(final.summary),
    )


def build_plan(
    graph: nx.MultiDiGraph,
    collected: Collected,
    rules: AiSignalsFile,
    started: datetime,
    tenant: str,
    source: Source,
    usage: Mapping[str, bool],
) -> tuple[Plan, Built]:
    """Decide everything to write. `usage` has one entry for each system in the graph and says
    whether it has usage records inside the lookback."""
    common: dict[str, Any] = {"tenant": tenant, "source": source}
    run_id = ids.discovery_run_id(started)
    functions = list(collected.functions)
    tags_of = collected.tags_by_arn

    # 4, 5. link and relate
    found = links(rules, functions, tags_of, collected.manifests, usage)
    related = relations(functions, collected.roles, collected.tables)
    listed = in_manifest(collected.manifests)

    # 3. score
    scores: dict[str, Score] = {}
    for function in functions:
        role = role_of(function, collected.roles)
        scores[function.name] = score(
            rules,
            function,
            tags_of.get(function.arn, {}),
            in_manifest=function.name in listed,
            iam_ai_action=role is not None
            and bool(granted_ai_actions(rules.ai_actions, role.statements)),
            usage=any(usage[s] for s in found[function.name].systems),
            trail_event=trail_shows_ai(
                role_name_of(function.role_arn),
                collected.trail_events,
                rules.trail_event_sources,
                rules.ai_actions,
            ),
        )

    # 2, 7. what each resource is, and what changed
    configs: dict[str, dict[str, Any]] = {}
    nodes: dict[str, AWSResource] = {}
    for table in collected.tables:
        rid, tags = table_id(table.name), dict(tags_of.get(table.arn, {}))
        configs[rid] = table_config(table, tags)
        nodes[rid] = AWSResource(
            id=rid, resource_type=TABLE, region=REGION, name=table.name, tags=tags, **common
        )
    for role in collected.roles:
        rid = role_id(role.name)
        configs[rid] = role_config(role)
        nodes[rid] = AWSResource(
            id=rid, resource_type=ROLE, region="global", name=role.name, **common
        )
    for function in functions:
        rid, tags = function_id(function.name), dict(tags_of.get(function.arn, {}))
        configs[rid] = function_config(function, tags)
        nodes[rid] = AWSResource(
            id=rid,
            resource_type=LAMBDA,
            region=REGION,
            name=function.name,
            tags=tags,
            env_var_names=list(function.env_names),
            ai_likelihood=scores[function.name].likelihood,
            signals=list(scores[function.name].signals),
            **common,
        )
    hashes = {rid: config_hash(config) for rid, config in configs.items()}
    nodes = {rid: n.model_copy(update={"config_hash": hashes[rid]}) for rid, n in nodes.items()}
    stored = {
        n: r
        for n in sorted(graph.nodes)
        if isinstance(r := node_record(graph, n), AWSResource) and r.source in CRAWLER_SOURCES
    }
    changed = diff(stored, hashes)
    fresh = {*changed.new, *changed.changed}

    plan = Plan(
        run=DiscoveryRun(
            id=run_id,
            mode=RunMode.FULL,
            started_at=started,
            crawler_version=CRAWLER_VERSION,
            **common,
        ),
        started=started,
        summary={},
    )
    ordered = [nodes[r] for r in sorted(nodes)]
    plan.roles_and_tables = [n for n in ordered if n.resource_type != LAMBDA]
    plan.functions = [n for n in ordered if n.resource_type == LAMBDA]
    plan.ended_resources = [
        stored[r].model_copy(update={"valid_to": started}) for r in changed.gone
    ]
    for rid in changed.changed:
        change = ChangeEvent(
            id=ids.change_event_id(run_id, rid),
            detected_at=started,
            previous_config_hash=stored[rid].config_hash,
            new_config_hash=hashes[rid],
            **common,
        )
        plan.changes.append((change, _edge(change.id, EdgeType.AFFECTS, rid, common)))
    plan.observed = [_edge(run_id, EdgeType.OBSERVED, rid, common) for rid in sorted(fresh)]

    # 5. relations
    wanted: list[Edge] = []
    for function in functions:
        for system in found[function.name].systems:
            wanted.append(_edge(system, EdgeType.RUNS_ON, function_id(function.name), common))
    wanted += [_edge(src, EdgeType.ASSUMES, dst, common) for src, dst in sorted(related.assumes)]
    wanted += [_edge(src, EdgeType.CALLS, dst, common) for src, dst in sorted(related.calls)]
    plan.relations = wanted
    keys = {e.key for e in wanted}
    plan.stale_relations = [
        edge
        for edge in _open_edges(graph, RELATION_EDGES)
        if edge.source in CRAWLER_SOURCES and edge.key not in keys
    ]

    # 4. candidates
    specs = candidates(scores, found)
    _plan_candidates(plan, graph, specs, found, common)

    # 6. evidence
    largest = _plan_evidence(plan, graph, collected, rules, found, nodes, configs, hashes, fresh)

    plan.summary = {
        "functions": len(functions),
        "roles": len(collected.roles),
        "tables": len(collected.tables),
        "resources_new": len(changed.new),
        "resources_changed": len(changed.changed),
        "resources_ended": len(changed.gone),
        "candidates": len(specs),
        "evidence_written": len(plan.evidence),
        "manifests_invalid": collected.manifests_invalid,
        "manifest_functions_missing": len(
            {n for m in collected.manifests for n in m.functions} - {f.name for f in functions}
        ),
        "trail_events": len(collected.trail_events),
        "largest_evidence_bytes": largest,
    }
    built = Built(
        functions=tuple(
            (f.name, scores[f.name].likelihood, scores[f.name].signals) for f in functions
        ),
        candidates=tuple((s.function, s.likelihood, s.signals) for s in specs),
        changes=changed.changed,
    )
    return plan, built


def _edge(src: str, edge_type: EdgeType, dst: str, common: Mapping[str, Any]) -> PlainEdge:
    return PlainEdge(src=src, dst=dst, type=edge_type, **common)


def _open_edges(graph: nx.MultiDiGraph, types: Collection[EdgeType]) -> list[Edge]:
    found = (data["record"] for _, _, data in graph.edges(data=True))
    return sorted((e for e in found if e.type in types), key=lambda e: tuple(map(str, e.key)))


def _plan_candidates(
    plan: Plan,
    graph: nx.MultiDiGraph,
    specs: Iterable[CandidateSpec],
    found: Mapping[str, Link],
    common: Mapping[str, Any],
) -> None:
    """Create or keep a Candidate for each spec. End one that stopped qualifying or whose
    function is gone. One whose function now runs a registered system stays open with
    `PROMOTED_TO`, because an open edge to an ended node is refused (ADR 0021, decision 12)."""
    wanted = {s.function for s in specs}
    for spec in specs:
        cid = ids.candidate_id(spec.function)
        plan.candidates.append(
            Candidate(
                id=cid,
                name=spec.function,
                ai_likelihood=spec.likelihood,
                signals=list(spec.signals),
                **common,
            )
        )
        plan.candidate_edges.append(
            _edge(cid, EdgeType.DERIVED_FROM, function_id(spec.function), common)
        )

    promoted: set[tuple[str, str]] = set()
    ended: set[str] = set()
    for node_id in sorted(graph.nodes):
        record = node_record(graph, node_id)
        if not (isinstance(record, Candidate) and record.source in CRAWLER_SOURCES):
            continue
        if record.name in wanted:
            continue
        systems = found.get(record.name, Link()).systems
        if systems:
            for system in systems:
                plan.candidate_edges.append(_edge(record.id, EdgeType.PROMOTED_TO, system, common))
                promoted.add((record.id, system))
        else:
            plan.ended_candidates.append(record.model_copy(update={"valid_to": plan.started}))
            ended.add(record.id)

    # A Candidate that qualifies again must not stay promoted. The edges of an ended one close
    # with it.
    for edge in _open_edges(graph, (EdgeType.PROMOTED_TO,)):
        kept = edge.src in ended or (edge.src, edge.dst) in promoted
        if edge.source in CRAWLER_SOURCES and not kept:
            plan.stale_candidate_edges.append(edge)


def _snapshot_content(
    config: Mapping[str, Any], digest: str, ai_actions: Iterable[str] = (), statements: int = 0
) -> tuple[dict[str, Any], int]:
    """The evidence content, and the size of the full one. Over the cap it is summarised and
    never refused (ADR 0021, decision 2): the hash still covers the whole config."""
    full = {"config": config, "config_hash": digest}
    size = len(canonical_json(full).encode())
    if size <= INLINE_EVIDENCE_MAX_BYTES:
        return full, size
    summary = {
        "truncated": True,
        "config_hash": digest,
        "ai_actions": list(ai_actions),
        "statement_count": statements,
    }
    return summary, size


def _plan_evidence(
    plan: Plan,
    graph: nx.MultiDiGraph,
    collected: Collected,
    rules: AiSignalsFile,
    found: Mapping[str, Link],
    nodes: Mapping[str, AWSResource],
    configs: Mapping[str, dict[str, Any]],
    hashes: Mapping[str, str],
    fresh: Collection[str],
) -> int:
    """Config snapshots, and the VC-060 check for each system that runs on a role. Evidence is
    written when there is none yet, when its content differs, when a resource it came from
    changed in this run, or when the latest has `evidence_refresh_days` or less left. Returns
    the size of the largest content before any summarising."""
    started = plan.started
    refresh = timedelta(days=rules.evidence_refresh_days)
    valid_until = started + timedelta(days=rules.evidence_valid_days)
    common = {"tenant": plan.run.tenant, "source": plan.run.source}
    latest = _latest_crawler_evidence(graph)
    stale = stale_evidence_ids(graph, started)  # a crash after a ChangeEvent must be repaired
    roles = {r.name: r for r in collected.roles}
    largest = 0

    def add(subject: str, kind: EvidenceKind, content: dict[str, Any], sources: list[str]) -> None:
        item = Evidence.build(
            subject=subject,
            collector=f"crawler@{CRAWLER_VERSION}",
            collected_at=started,
            valid_until=valid_until,
            kind=kind,
            content=content,
            **common,
        )
        edges: list[Edge] = [_edge(item.id, EdgeType.ABOUT, subject, common)]
        edges += [_edge(item.id, EdgeType.COLLECTED_FROM, s, common) for s in sources]
        plan.evidence.append((item, edges))

    for rid in sorted(configs):
        node, ai, statements = nodes[rid], (), ()
        if node.resource_type == ROLE:
            statements = roles[node.name].statements
            ai = granted_ai_actions(rules.ai_actions, statements)
        content, size = _snapshot_content(configs[rid], hashes[rid], ai, len(statements))
        largest = max(largest, size)
        last = latest.get((rid, EvidenceKind.CONFIG_SNAPSHOT, None))
        if (
            rid in fresh
            or last is None
            or (last.content or {}).get("config_hash") != hashes[rid]
            or expiring(last, started, refresh)
            or last.id in stale
        ):
            add(rid, EvidenceKind.CONFIG_SNAPSHOT, content, [rid])

    # VC-060: capability without usage, from CloudTrail only (ADR 0021, decision 9).
    by_name = {f.name: f for f in collected.functions}
    for system in sorted({s for link in found.values() for s in link.systems}):
        reached: dict[str, CollectedRole] = {}
        unseen = 0
        sources: set[str] = set()
        for name in sorted(n for n, link in found.items() if system in link.systems):
            role = role_of(by_name[name], collected.roles)
            sources.add(function_id(name))
            if role is None:
                unseen += 1  # a later run that can see the role must check again
            else:
                reached[role.name] = role
                sources.add(role_id(role.name))
        check = check_vc060(
            rules.ai_actions,
            reached.values(),
            collected.trail_events,
            rules.trail_event_sources,
            unseen,
        )
        content = check.content(system)
        largest = max(largest, len(canonical_json(content).encode()))
        last = latest.get((system, EvidenceKind.AUTOMATED_TEST, CONTROL))
        if (
            last is None
            or last.sha256 != content_sha256(content)
            or expiring(last, started, refresh)
            or last.id in stale
            or sources & set(fresh)
            or {e.dst for e in out_edges(graph, last.id, EdgeType.COLLECTED_FROM)} != sources
        ):
            add(system, EvidenceKind.AUTOMATED_TEST, content, sorted(sources))
    return largest


def _latest_crawler_evidence(
    graph: nx.MultiDiGraph,
) -> dict[tuple[str, EvidenceKind, str | None], Evidence]:
    """The newest crawler Evidence for each subject and kind, and for a check also its control."""
    newest: dict[tuple[str, EvidenceKind, str | None], Evidence] = {}
    for node_id in sorted(graph.nodes):
        item = node_record(graph, node_id)
        if not (isinstance(item, Evidence) and item.collector.startswith("crawler@")):
            continue
        control = (item.content or {}).get("control")
        key = (item.subject, item.kind, control if isinstance(control, str) else None)
        if key not in newest or (item.collected_at, item.id) > (
            newest[key].collected_at,
            newest[key].id,
        ):
            newest[key] = item
    return newest
