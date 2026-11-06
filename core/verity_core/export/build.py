"""Builds the snapshot from a graph and writes it only if the scan passes (ADR 0029, ADR 0030).

Reads nothing from AWS: the graph comes from `GraphRepository.load_graph()`, supplied by the
caller. The same graph and `as_of` give identical bytes.
"""

import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import networkx as nx

from verity_core.assess.apply import estimate_apply
from verity_core.content.loader import Content
from verity_core.export.commits import without_commits
from verity_core.export.derive import derive
from verity_core.export.redact import OWN_ACCOUNT, Redacted, RedactionReport, redact
from verity_core.export.scan import Hit, scan_text
from verity_core.export.snapshot import DataSource, Snapshot
from verity_core.model.enums import EvidenceKind, Source
from verity_core.model.nodes import Evidence, Provider

MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
_SIGN_OFF_KINDS = (EvidenceKind.ATTESTATION, EvidenceKind.DOCUMENT_REF)


class StaleGraphError(ValueError):
    """The stored assessments are not the ones an assessment now would produce, so the file would
    not match the graph. The message holds counts only."""

    def __init__(self, written: Counter[str]):
        kinds = ", ".join(f"{n} {kind}" for kind, n in sorted(written.items()))
        super().__init__(f"an assessment would still write {kinds}: run verity assess first")
        self.written = written


class SnapshotTooLarge(ValueError):
    """Over the limit the dashboard is designed for. The message holds a size only."""


class ScanRejected(Exception):
    """The scan found something. Carries the hits (category and path only); nothing was written."""

    def __init__(self, hits: list[Hit]):
        super().__init__(f"{len(hits)} scan hit(s)")
        self.hits = hits


@dataclass(frozen=True)
class Built:
    snapshot: Snapshot
    redacted: Redacted

    @property
    def report(self) -> RedactionReport:
        return self.redacted.report


def _ticking_clock(graph: nx.MultiDiGraph, start: datetime) -> Callable[[], datetime]:
    """A clock that moves forward on every call, from a time after anything in the graph. The
    estimate counts a record as written if it was stamped after the run began, so a clock that
    stood still would count every copied record."""
    stamps = [graph.nodes[n]["record"].updated_at for n in graph.nodes]
    now = max([start, *(stamp for stamp in stamps if stamp is not None)])

    def clock() -> datetime:
        nonlocal now
        now += timedelta(microseconds=1)
        return now

    return clock


def _simulated_components(graph: nx.MultiDiGraph) -> list[str]:
    """What in the file is not real: simulated providers, simulated sign-offs, and how many
    records are synthetic or simulated. The people, companies and decisions are all invented."""
    records = [graph.nodes[n]["record"] for n in graph.nodes]
    found = {f"provider: {r.name}" for r in records if isinstance(r, Provider) and r.simulated}
    signed = [
        r
        for r in records
        if isinstance(r, Evidence) and r.source is Source.SIMULATED and r.kind in _SIGN_OFF_KINDS
    ]
    if signed:
        found.add("simulated sign-offs")
    sources = Counter(r.source for r in records)
    if sources[Source.SYNTHETIC]:
        found.add(f"{sources[Source.SYNTHETIC]} synthetic records (invented organisation data)")
    if sources[Source.SIMULATED]:
        found.add(f"{sources[Source.SIMULATED]} simulated records")
    return sorted(found)


def _steps(report: RedactionReport) -> list[str]:
    steps = ["config hash fields withheld", "only listed tags and content keys published"]
    if report.own_account_found:
        steps.append(f"own account replaced by {OWN_ACCOUNT}")
    if report.external_accounts:
        steps.append("other accounts replaced by ordinals")
    if report.evidence_rebuilt:
        steps.append("changed Evidence rebuilt with a new hash and ID")
    steps.append("independent scan before writing")
    return steps


def build_snapshot(
    graph: nx.MultiDiGraph,
    *,
    content: Content,
    as_of: datetime,
    data_source: DataSource,
    decision_commits: list[dict[str, Any]] | None = None,
) -> Built:
    """Refuses a graph whose stored assessments are not the ones `as_of` would give (decision 2).
    Findings, statuses and control results come from that same run. `decision_commits` are the
    looked-up rows (decision 9); without them every `commit_sha` is null."""
    if content.rules is None:
        raise ValueError("applicability.yaml is needed to check the assessments")
    result = estimate_apply(
        graph,
        content.rules,
        content.dates,
        as_of,
        _ticking_clock(graph, as_of),
        content.tenant,
    )
    if result.total_written:
        raise StaleGraphError(result.written)
    derived = derive(graph, result)
    derived["decision_commits"] = (
        decision_commits if decision_commits is not None else without_commits(graph)
    )
    redacted = redact(graph, derived)
    report = redacted.report
    if data_source == "live" and not report.own_account_found:
        raise ValueError("a live graph must show the owner's account")
    snapshot = Snapshot.model_validate(
        {
            "header": {
                "as_of": as_of,
                "data_source": data_source,
                "redaction": {
                    "steps": _steps(report),
                    "own_account_replaced": report.own_account_found,
                    "external_accounts": report.external_accounts,
                    "content_keys_withheld": report.content_keys_withheld,
                    "tags_withheld": report.tags_withheld,
                    "evidence_rebuilt": report.evidence_rebuilt,
                    "evidence_unchanged": report.evidence_unchanged,
                },
                "simulated_components": _simulated_components(graph),
            },
            "nodes": redacted.nodes,
            "edges": redacted.edges,
            **redacted.extras,
        }
    )
    return Built(snapshot, redacted)


def serialise(snapshot: Snapshot) -> str:
    """Stable bytes: sorted keys, compact, UTF-8 and a final newline."""
    data = snapshot.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def write_snapshot(path: Path | str, built: Built) -> int:
    """Scans the text first, so nothing unscanned ever touches the disk, not even after a crash.
    Then writes to a temporary file in the same folder, flushes it and renames it into place.
    Returns the size in bytes. On a hit, or any error, no new file is left behind."""
    text = serialise(built.snapshot)
    hits = scan_text(text, old_hashes=built.redacted.replaced_hashes)
    if hits:
        raise ScanRejected(hits)
    data = text.encode("utf-8")
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise SnapshotTooLarge(f"{len(data)} bytes is over {MAX_SNAPSHOT_BYTES}")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=target.parent, prefix=".snapshot-", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o644)  # `mkstemp` makes it private, and this file is meant to be read
        os.replace(temporary, target)
        return len(data)
    finally:
        temporary.unlink(missing_ok=True)
