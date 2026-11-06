"""Config hashes and what changed since the last run (architecture section D, stage 7).
Pure.

A hash covers the full normalised config, so change detection never depends on how much of it
evidence keeps (ADR 0021, decision 2). Every list is sorted, or each crawl would see a change.
Left out on purpose: a function's `LastModified`, and its `RevisionId`, which moves when an env
var value changes (the values are never read).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from verity_core.discovery.boundary import (
    CollectedFunction,
    CollectedRole,
    CollectedTable,
    Statement,
)
from verity_core.model.evidence import Evidence
from verity_core.model.hashing import canonical_json, sha256_hex
from verity_core.model.nodes import AWSResource


def config_hash(config: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json(config))


def function_config(function: CollectedFunction, tags: Mapping[str, str]) -> dict[str, Any]:
    return {
        "runtime": function.runtime,
        "architectures": list(function.architectures),
        "handler": function.handler,
        "role": function.role_arn,
        "memory_mb": function.memory_mb,
        "timeout_s": function.timeout_s,
        "env_names": list(function.env_names),
        "code_sha256": function.code_sha256,
        "tags": dict(sorted(tags.items())),
    }


def _statement(statement: Statement) -> dict[str, Any]:
    return {
        "effect": statement.effect,
        "actions": list(statement.actions),
        "resources": list(statement.resources),
        "negated": statement.negated,
    }


def role_config(role: CollectedRole) -> dict[str, Any]:
    return {
        "trust": [
            {"effect": t.effect, "principals": list(t.principals), "actions": list(t.actions)}
            for t in role.trust
        ],
        "policies": [
            {"name": p.name, "kind": p.kind, "statements": [_statement(s) for s in p.statements]}
            for p in role.policies
        ],
    }


def table_config(table: CollectedTable, tags: Mapping[str, str]) -> dict[str, Any]:
    return {"name": table.name, "tags": dict(sorted(tags.items()))}


@dataclass(frozen=True)
class Diff:
    new: tuple[str, ...]  # resource IDs not in the graph
    changed: tuple[str, ...]  # in the graph, with a different config hash
    gone: tuple[str, ...]  # in the graph, not seen this run


def diff(stored: Mapping[str, AWSResource], current: Mapping[str, str]) -> Diff:
    """`stored` holds the open resources in the graph, `current` the hash of each one seen now."""
    return Diff(
        new=tuple(sorted(i for i in current if i not in stored)),
        changed=tuple(
            sorted(i for i, h in current.items() if i in stored and stored[i].config_hash != h)
        ),
        gone=tuple(sorted(i for i in stored if i not in current)),
    )


def expiring(latest: Evidence | None, now: datetime, refresh: timedelta) -> bool:
    """True when there is no evidence yet, or the latest item has `refresh` or less left to run
    (ADR 0021, decision 1). Comparing its content is the caller's job."""
    return latest is None or latest.valid_until - now <= refresh
