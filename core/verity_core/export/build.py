"""Builds the snapshot from a graph and writes it only if the scan passes (ADR 0029).

Reads nothing from AWS: the graph comes from `GraphRepository.load_graph()`, supplied by the
caller. The same graph and `as_of` give identical bytes.
"""

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import networkx as nx

from verity_core.export.redact import Redacted, RedactionReport, redact
from verity_core.export.scan import Hit, scan_text
from verity_core.export.snapshot import DataSource, Snapshot


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


def build_snapshot(graph: nx.MultiDiGraph, *, as_of: datetime, data_source: DataSource) -> Built:
    redacted = redact(graph)
    snapshot = Snapshot.model_validate(
        {
            "data_source": data_source,
            "as_of": as_of,
            "nodes": redacted.nodes,
            "edges": redacted.edges,
        }
    )
    return Built(snapshot, redacted)


def serialise(snapshot: Snapshot) -> str:
    """Stable bytes: sorted keys, compact, UTF-8 and a final newline."""
    data = snapshot.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def write_snapshot(path: Path | str, built: Built) -> int:
    """Writes to a temporary file in the same folder, scans what was written, and renames it
    into place only if the scan is clean. Returns the size in bytes. On a hit, or any error, no
    file is left behind."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=target.parent, prefix=".snapshot-", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialise(built.snapshot))
        hits = scan_text(
            temporary.read_text(encoding="utf-8"), old_hashes=built.redacted.replaced_hashes
        )
        if hits:
            raise ScanRejected(hits)
        size = temporary.stat().st_size
        os.replace(temporary, target)
        return size
    finally:
        temporary.unlink(missing_ok=True)
