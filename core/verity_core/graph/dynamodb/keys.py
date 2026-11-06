"""The single-table key design (docs/architecture.md section H, ADR 0012).

| Item                  | PK                       | SK                                  |
|-----------------------|--------------------------|-------------------------------------|
| Node                  | `T#{tenant}#N#{id}`      | `META`                              |
| Outgoing edge         | `T#{tenant}#N#{src}`     | `E#{type}#{dst}[#{qualifier}]`      |
| Reverse edge (mirror) | `T#{tenant}#N#{dst}`     | `R#{type}#{src}[#{qualifier}]`      |
| Node history          | `T#{tenant}#N#{id}`      | `H#{iso_ts}#{version}`              |
| Usage record          | `T#{tenant}#U#{system}`  | `U#{iso_ts}#{usage_id}`             |

IDs, tenants and qualifiers contain no `#` (their patterns forbid it), so a key can always be
read back unambiguously. Timestamps are fixed-width UTC, and versions are zero-padded, so
sorting keys as strings sorts them chronologically.
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from verity_core.model.edges import EdgeKey
from verity_core.model.enums import EdgeType, NodeType

META = "META"
GSI1 = "GSI1"

Kind = Literal["META", "E", "R", "H", "U"]

_VERSION_WIDTH = 10


def format_ts(value: datetime) -> str:
    """`2026-11-05T09:00:00.000000Z`: UTC, fixed width, so string order is time order."""
    if value.tzinfo is None:
        raise ValueError("timestamps in keys must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def tenant_prefix(tenant: str) -> str:
    """Every item of a tenant has a PK that starts with this."""
    return f"T#{tenant}#"


def node_pk(tenant: str, node_id: str) -> str:
    return f"{tenant_prefix(tenant)}N#{node_id}"


def usage_pk(tenant: str, system_id: str) -> str:
    """Usage has its own partition, so an app role's `dynamodb:LeadingKeys` condition can name it
    without also reaching the system's `META`, edge and history items (ADR 0024)."""
    return f"{tenant_prefix(tenant)}U#{system_id}"


def _with_qualifier(sk: str, qualifier: str | None) -> str:
    return f"{sk}#{qualifier}" if qualifier else sk


def edge_sk(key: EdgeKey) -> str:
    return _with_qualifier(f"E#{key.type.value}#{key.dst}", key.qualifier)


def reverse_sk(key: EdgeKey) -> str:
    return _with_qualifier(f"R#{key.type.value}#{key.src}", key.qualifier)


def edge_prefix(edge_type: EdgeType | None = None) -> str:
    """For `begins_with` on a node's outgoing edges, optionally of one type."""
    return "E#" if edge_type is None else f"E#{edge_type.value}#"


def reverse_prefix(edge_type: EdgeType | None = None) -> str:
    return "R#" if edge_type is None else f"R#{edge_type.value}#"


def history_sk(updated_at: datetime, version: int) -> str:
    return f"H#{format_ts(updated_at)}#{version:0{_VERSION_WIDTH}d}"


def usage_sk(timestamp: datetime, usage_id: UUID) -> str:
    return f"U#{format_ts(timestamp)}#{usage_id}"


def usage_sk_range(since: datetime | None, until: datetime | None) -> tuple[str, str]:
    """Bounds for a `BETWEEN` query that select exactly `[since, until)`.

    DynamoDB's `BETWEEN` is inclusive at both ends. A usage key is `U#{ts}#{id}`, which sorts
    after the bare `U#{ts}`, so using that as the upper bound leaves out records stamped
    exactly `until`, and using it as the lower bound keeps records stamped exactly `since`.
    """
    low = "U#" if since is None else f"U#{format_ts(since)}"
    high = "U$" if until is None else f"U#{format_ts(until)}"  # "$" sorts just after "#"
    return low, high


def gsi_type_pk(tenant: str, node_type: NodeType) -> str:
    return f"{tenant_prefix(tenant)}TYPE#{node_type.value}"


def kind_of(sk: str) -> Kind:
    """What an item is, from its sort key."""
    if sk == META:
        return "META"
    prefix = sk[:2]
    if prefix in ("E#", "R#", "H#", "U#"):
        return prefix[0]  # type: ignore[return-value]
    raise ValueError(f"unknown sort key {sk!r}")
