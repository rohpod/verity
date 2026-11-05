"""Turn records into DynamoDB items and back (ADR 0013).

Every item holds the whole record as a JSON string in `doc`. Reading it back goes through the
same pydantic models as everything else, so nothing depends on how the AWS SDK represents
numbers: boto3 returns them as `Decimal`, which would break evidence hashes.

Items use the SDK's low-level typed form (`{"S": ...}`, `{"N": ...}`) and are built here
without any AWS import. `ver` is a plain number beside `doc`, because a condition expression
cannot look inside a JSON string and writes check the version they read.
"""

import json
from typing import Any

from verity_core.graph.dynamodb import keys
from verity_core.model.edges import Edge, parse_edge
from verity_core.model.nodes import Node, parse_node
from verity_core.model.usage import UsageRecord

Item = dict[str, dict[str, str]]


def _s(value: str) -> dict[str, str]:
    return {"S": value}


def _n(value: int) -> dict[str, str]:
    return {"N": str(value)}


def _doc(record: Any) -> dict[str, str]:
    return _s(record.model_dump_json())


def node_item(node: Node) -> Item:
    """The `META` item: the current version, with the keys that list nodes by type."""
    return {
        "PK": _s(keys.node_pk(node.tenant, node.id)),
        "SK": _s(keys.META),
        "doc": _doc(node),
        "ver": _n(node.version),
        "GSI1PK": _s(keys.gsi_type_pk(node.tenant, node.type)),
        "GSI1SK": _s(node.id),
    }


def history_item(node: Node) -> Item:
    """One `H#` item per real version. Evidence never gets one: it never changes."""
    if node.updated_at is None:
        raise ValueError("only a stored node (one with updated_at) has a history entry")
    return {
        "PK": _s(keys.node_pk(node.tenant, node.id)),
        "SK": _s(keys.history_sk(node.updated_at, node.version)),
        "doc": _doc(node),
        "ver": _n(node.version),
    }


def edge_items(edge: Edge) -> tuple[Item, Item]:
    """The outgoing `E#` item and its reverse `R#` mirror, which are always written together."""
    forward = {
        "PK": _s(keys.node_pk(edge.tenant, edge.src)),
        "SK": _s(keys.edge_sk(edge.key)),
        "doc": _doc(edge),
        "ver": _n(edge.version),
    }
    reverse = {
        "PK": _s(keys.node_pk(edge.tenant, edge.dst)),
        "SK": _s(keys.reverse_sk(edge.key)),
        "doc": forward["doc"],
        "ver": forward["ver"],
    }
    return forward, reverse


def usage_item(record: UsageRecord) -> Item:
    return {
        "PK": _s(keys.node_pk(record.tenant, record.system_id)),
        "SK": _s(keys.usage_sk(record.timestamp, record.usage_id)),
        "doc": _doc(record),
    }


def _load(item: Item) -> Any:
    return json.loads(item["doc"]["S"])


def node_from_item(item: Item) -> Node:
    return parse_node(_load(item))


def edge_from_item(item: Item) -> Edge:
    return parse_edge(_load(item))


def usage_from_item(item: Item) -> UsageRecord:
    return UsageRecord.model_validate(_load(item))
