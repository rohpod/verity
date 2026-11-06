"""Where the raw estate comes from. A collector hands back `Collected`, already cleaned by
`boundary.py`, and says which `Source` its records carry (ADR 0021, decision 4)."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from verity_core.discovery.boundary import (
    CollectedFunction,
    CollectedManifest,
    CollectedRole,
    CollectedTable,
    TrailEvent,
    clean_function,
    clean_manifest,
    clean_role,
    clean_table,
    clean_tags,
    clean_trail_event,
)
from verity_core.model.enums import Source

REGION = "eu-north-1"


@dataclass(frozen=True)
class Collected:
    functions: tuple[CollectedFunction, ...] = ()
    roles: tuple[CollectedRole, ...] = ()
    tables: tuple[CollectedTable, ...] = ()
    manifests: tuple[CollectedManifest, ...] = ()
    trail_events: tuple[TrailEvent, ...] = ()
    tags_by_arn: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    manifests_invalid: int = 0  # counted, never kept


@runtime_checkable
class Collector(Protocol):
    source: Source

    def collect(self) -> Collected: ...


def clean_estate(raw: Mapping[str, Any], region: str = REGION) -> Collected:
    """A whole recorded estate in the shape of the AWS responses (`estate.json`)."""
    manifests = [clean_manifest(m) for m in raw.get("manifests", ())]
    return Collected(
        functions=tuple(clean_function(f) for f in raw.get("functions", ())),
        roles=tuple(
            clean_role(r["role"], r.get("inline_policies", ()), r.get("attached_policies", ()))
            for r in raw.get("roles", ())
        ),
        tables=tuple(clean_table(name, region) for name in raw.get("tables", ())),
        manifests=tuple(m for m in manifests if m is not None),
        trail_events=tuple(clean_trail_event(e) for e in raw.get("trail_events", ())),
        tags_by_arn=clean_tags(raw.get("tag_mappings", ())),
        manifests_invalid=sum(m is None for m in manifests),
    )


class FixtureCollector:
    """Reads a recorded estate from a JSON file. Nothing is read from AWS, and every record it
    leads to is `simulated`, so a fixture run never looks live-discovered."""

    source = Source.SIMULATED

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def collect(self) -> Collected:
        return clean_estate(json.loads(self.path.read_text(encoding="utf-8")))
