"""The rules for writing to the graph, as pure functions (ADR 0013).

Each takes the stored record (or None), the incoming record and `now`, and returns what to
store. They read no clock and touch no storage, so `InMemoryRepository` and
`DynamoDBRepository` apply exactly the same decisions and differ only in how they persist.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from verity_core.graph.errors import ImmutableNodeError, TenantMismatchError
from verity_core.model.edges import Edge
from verity_core.model.evidence import Evidence
from verity_core.model.hashing import content_hash
from verity_core.model.nodes import Node
from verity_core.model.usage import UsageRecord


class WriteAction(StrEnum):
    INSERT = "insert"
    UPDATE = "update"  # includes reopening a closed edge and closing an open one
    NOOP = "noop"  # nothing changed, so nothing is written (D14)


@dataclass(frozen=True)
class NodePlan:
    action: WriteAction
    node: Node  # what to store, or the stored node itself for a no-op


@dataclass(frozen=True)
class EdgePlan:
    action: WriteAction
    edge: Edge


# --- small checks and helpers --------------------------------------------------------------


def require_aware(value: datetime, message: str) -> None:
    if value.tzinfo is None:
        raise ValueError(message)


def read_clock(clock: Callable[[], datetime]) -> datetime:
    """Call the injected clock once. Nothing else reads time (D5)."""
    now = clock()
    require_aware(now, "the clock must return timezone-aware datetimes")
    return now.astimezone(UTC)


def ensure_tenant(expected: str, actual: str, label: str) -> None:
    if actual != expected:
        raise TenantMismatchError(f"{label} is in tenant {actual!r}, not {expected!r}")


def reject_future_end(valid_to: datetime | None, now: datetime) -> None:
    """`as_of=None` means "open" and reads no clock, so a future end would make a record
    vanish early (ADR 0012)."""
    if valid_to is not None and valid_to > now:
        raise ValueError(f"valid_to {valid_to} is in the future")


def with_changes[R: BaseModel](record: R, **updates: Any) -> R:
    """Copy with changes, validated again (for example `valid_to` must not precede `valid_from`)."""
    return type(record).model_validate({**record.model_dump(), **updates})


def period_start(edge: Edge, after: datetime | None, fallback: datetime) -> datetime:
    """The edge's `valid_from`, unless it is absent or stale (earlier than `after`)."""
    start = edge.valid_from
    if start is None or (after is not None and start < after):
        return fallback
    return start


# --- nodes ---------------------------------------------------------------------------------


def plan_node_write(existing: Node | None, node: Node, now: datetime) -> NodePlan:
    """New nodes get version 1. A real change bumps the version. An unchanged node is a no-op.
    Evidence is immutable: collecting again creates a new node."""
    reject_future_end(node.valid_to, now)
    if existing is None:
        stored = with_changes(node, created_at=now, updated_at=now, version=1)
        if stored.valid_from is None:
            stored = with_changes(stored, valid_from=now)
        return NodePlan(WriteAction.INSERT, stored)

    # A caller that does not know `valid_from` leaves it unset; keep the stored one.
    candidate = node if node.valid_from else with_changes(node, valid_from=existing.valid_from)
    if content_hash(candidate) == content_hash(existing):
        return NodePlan(WriteAction.NOOP, existing)
    if isinstance(existing, Evidence):
        raise ImmutableNodeError(f"{node.id!r} is Evidence; collect new evidence instead")
    stored = with_changes(
        candidate, created_at=existing.created_at, updated_at=now, version=existing.version + 1
    )
    return NodePlan(WriteAction.UPDATE, stored)


# --- edges ---------------------------------------------------------------------------------


def plan_edge_write(existing: Edge | None, edge: Edge, now: datetime) -> EdgePlan:
    """New edges get version 1. An open edge sent for a closed one reopens it. A closed edge
    sent again, or an open edge sent unchanged, is a no-op."""
    reject_future_end(edge.valid_to, now)
    if existing is None:
        stored = with_changes(edge, created_at=now, updated_at=now, version=1)
        if stored.valid_from is None:
            stored = with_changes(stored, valid_from=now)
        return EdgePlan(WriteAction.INSERT, stored)

    if existing.valid_to is not None and edge.valid_to is None:
        return EdgePlan(WriteAction.UPDATE, _reopen(existing, edge, now))

    last_end = existing.closed_intervals[-1][1] if existing.closed_intervals else None
    candidate = with_changes(
        edge,
        valid_from=period_start(edge, last_end, existing.valid_from),
        closed_intervals=existing.closed_intervals,
    )
    if content_hash(candidate) == content_hash(existing):
        return EdgePlan(WriteAction.NOOP, existing)
    stored = with_changes(
        candidate, created_at=existing.created_at, updated_at=now, version=existing.version + 1
    )
    return EdgePlan(WriteAction.UPDATE, stored)


def _reopen(existing: Edge, edge: Edge, now: datetime) -> Edge:
    """Keep the finished period in `closed_intervals` and start a new one."""
    start = period_start(edge, existing.valid_to, now)
    if start < existing.valid_to:
        raise ValueError(f"{edge.key} cannot reopen at {start}, before it closed")
    return with_changes(
        edge,
        created_at=existing.created_at,
        updated_at=now,
        version=existing.version + 1,
        valid_from=start,
        closed_intervals=(*existing.closed_intervals, (existing.valid_from, existing.valid_to)),
    )


def plan_close_edge(existing: Edge, valid_to: datetime, now: datetime) -> EdgePlan:
    """Closing an already closed edge keeps its first `valid_to`."""
    if existing.valid_to is not None:
        return EdgePlan(WriteAction.NOOP, existing)
    reject_future_end(valid_to, now)
    stored = with_changes(existing, valid_to=valid_to, updated_at=now, version=existing.version + 1)
    return EdgePlan(WriteAction.UPDATE, stored)


def edges_to_close(node: Node, open_edges: Iterable[Edge]) -> list[tuple[Edge, datetime]]:
    """An ended node takes its open edges with it. Each closes when the node ended, or when
    the edge began if that is later, so no edge ends before it starts."""
    return [(edge, max(node.valid_to, edge.valid_from)) for edge in open_edges]


# --- usage ---------------------------------------------------------------------------------


def usage_identity(record: UsageRecord) -> tuple[datetime, str]:
    """The same identity as the DynamoDB key `U#{iso_ts}#{usage_id}`: the first write wins."""
    return (record.timestamp, str(record.usage_id))


def check_usage_bounds(since: datetime | None, until: datetime | None) -> None:
    for bound in (since, until):
        if bound is not None:
            require_aware(bound, "since and until must be timezone-aware")
