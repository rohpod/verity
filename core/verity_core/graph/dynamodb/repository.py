"""`DynamoDBRepository`: the graph in the `verity-graph` table (ADR 0003, ADR 0013).

Every write decision comes from `planning.py`, the same code `InMemoryRepository` uses; this
class only reads items, asks for a plan, and writes it. Only this package may import boto3
(ADR 0014).

Writes check the version they read, so a stale write fails with `ConcurrentWriteError` instead
of overwriting. A node and its history entry are written in one transaction.
"""

import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import networkx as nx
from botocore.exceptions import ClientError

from verity_core.graph.dynamodb import items, keys
from verity_core.graph.dynamodb.client import default_client
from verity_core.graph.dynamodb.table import TABLE_NAME
from verity_core.graph.dynamodb.usage import DynamoDBUsageSink
from verity_core.graph.errors import ConcurrentWriteError, EdgeNotFoundError, RepositoryError
from verity_core.graph.loader import build_graph, version_at
from verity_core.graph.planning import (
    WriteAction,
    check_usage_bounds,
    edges_to_close,
    ensure_tenant,
    plan_close_edge,
    plan_edge_write,
    plan_node_write,
    read_clock,
    require_aware,
)
from verity_core.model.edges import Edge, EdgeKey
from verity_core.model.enums import Direction, EdgeType, NodeType
from verity_core.model.evidence import Evidence
from verity_core.model.nodes import Node
from verity_core.model.usage import UsageRecord
from verity_core.model.validation import EDGE_RULES, validate_edge, validate_node_change

_BATCH_GET_LIMIT = 100
# Items per page of the full-table scan. At about 0.6 KB an item, a page is roughly the
# table's 15 read units for one second, so a scan paces itself instead of asking for 1 MB at once.
_SCAN_PAGE_ITEMS = 100
# A transaction holds 100 actions and an edge is two (`E#` and `R#`), so 50 edges at most.
_EDGES_PER_TRANSACTION = 50
_BATCH_GET_ATTEMPTS = 6
_KEY = "ConsistentRead"
# boto3's retries do not cover a transaction that DynamoDB cancels for lack of capacity (it
# raises TransactionCanceledException, which is not in botocore's list of throttling errors),
# so the repository retries those itself. A cancelled transaction wrote nothing, and the version
# conditions are checked again on each attempt, so repeating it is safe. The pauses add up to
# about 22 s, long enough for a 15-unit table to refill a 50-edge chunk.
_THROTTLE_REASONS = frozenset({"ProvisionedThroughputExceeded", "ThrottlingError"})
_TRANSACTION_ATTEMPTS = 8
_TRANSACTION_PAUSE = 0.2
_TRANSACTION_PAUSE_CAP = 10.0


def _is_conflict(error: ClientError) -> bool:
    """Did a condition fail, or did another transaction touch the same item?"""
    code = error.response["Error"]["Code"]
    if code == "ConditionalCheckFailedException":
        return True
    if code == "TransactionCanceledException":
        reasons = error.response.get("CancellationReasons") or []
        return any(
            r.get("Code") in ("ConditionalCheckFailed", "TransactionConflict") for r in reasons
        )
    return False


def _is_throttle(error: ClientError) -> bool:
    """Was a transaction cancelled only because the table ran out of capacity? A conflict
    anywhere in it means the data changed, which retrying the same write would not fix."""
    if error.response["Error"]["Code"] != "TransactionCanceledException" or _is_conflict(error):
        return False
    reasons = {r.get("Code") for r in error.response.get("CancellationReasons") or []}
    return bool(reasons & _THROTTLE_REASONS)


class DynamoDBRepository:
    def __init__(
        self,
        tenant: str,
        clock: Callable[[], datetime],
        *,
        client: Any = None,
        table_name: str = TABLE_NAME,
        sleep: Callable[[float], None] = time.sleep,
        scan_page_items: int = _SCAN_PAGE_ITEMS,
    ):
        self.tenant = tenant
        self._clock = clock
        self._client = client if client is not None else default_client()
        self._table = table_name
        self._sleep = sleep
        self._scan_page_items = scan_page_items
        self._usage = DynamoDBUsageSink(tenant, client=self._client, table_name=table_name)

    # --- low-level reads -----------------------------------------------------------------

    def _get_item(self, pk: str, sk: str) -> items.Item | None:
        response = self._client.get_item(
            TableName=self._table,
            Key={"PK": {"S": pk}, "SK": {"S": sk}},
            ConsistentRead=True,
        )
        return response.get("Item")

    def _query(self, **kwargs: Any) -> Iterator[items.Item]:
        """Every item a query matches, following pagination."""
        start: dict[str, Any] | None = None
        while True:
            page = self._client.query(
                TableName=self._table,
                **kwargs,
                **({"ExclusiveStartKey": start} if start else {}),
            )
            yield from page.get("Items", [])
            start = page.get("LastEvaluatedKey")
            if not start:
                return

    def _partition(self, node_id: str, prefix: str) -> Iterator[items.Item]:
        """A node's items whose sort key starts with `prefix`, in sort-key order."""
        return self._query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues={
                ":pk": {"S": keys.node_pk(self.tenant, node_id)},
                ":prefix": {"S": prefix},
            },
            ConsistentRead=True,
        )

    # --- nodes ---------------------------------------------------------------------------

    def get_node(self, node_id: str) -> Node | None:
        item = self._get_item(keys.node_pk(self.tenant, node_id), keys.META)
        return items.node_from_item(item) if item else None

    def upsert_node(self, node: Node) -> Node:
        ensure_tenant(self.tenant, node.tenant, repr(node.id))
        item = self._get_item(keys.node_pk(self.tenant, node.id), keys.META)
        existing = items.node_from_item(item) if item else None
        validate_node_change(
            node,
            open_edges=self._open_edges_touching(node) if _reads_edges(node) else [],
            organisation_ids=(
                self._ids_by_type(NodeType.ORGANISATION)
                if node.type is NodeType.ORGANISATION
                else []
            ),
        )
        plan = plan_node_write(existing, node, read_clock(self._clock))
        if plan.action is WriteAction.NOOP:
            return plan.node
        stored = plan.node
        if stored.valid_to is not None:
            # Close the edges first. A run that fails part way can simply be repeated, because
            # closing a closed edge changes nothing (ADR 0013).
            self._close_edges_of(stored)
        self._write_node(stored, expected_version=existing.version if existing else None)
        return stored

    def _transact(self, actions: list[dict[str, Any]]) -> None:
        """`TransactWriteItems`, repeated with backoff while cancelled for lack of capacity."""
        for attempt in range(_TRANSACTION_ATTEMPTS):
            try:
                self._client.transact_write_items(TransactItems=actions)
                return
            except ClientError as error:
                if not _is_throttle(error) or attempt + 1 == _TRANSACTION_ATTEMPTS:
                    raise
                self._sleep(min(_TRANSACTION_PAUSE * 2**attempt, _TRANSACTION_PAUSE_CAP))

    def _write_node(self, node: Node, *, expected_version: int | None) -> None:
        """Insert (`expected_version=None`) or replace the version that was read.

        Evidence never changes, so it is one conditional write with no `H#` item. Anything else
        writes `META` and its `H#` entry together, or neither.
        """
        meta = items.node_item(node)
        if expected_version is None:
            condition = {"ConditionExpression": "attribute_not_exists(PK)"}
        else:
            condition = {
                "ConditionExpression": "ver = :expected",
                "ExpressionAttributeValues": {":expected": {"N": str(expected_version)}},
            }
        try:
            if isinstance(node, Evidence):
                self._client.put_item(TableName=self._table, Item=meta, **condition)
            else:
                self._transact(
                    [
                        {"Put": {"TableName": self._table, "Item": meta, **condition}},
                        {"Put": {"TableName": self._table, "Item": items.history_item(node)}},
                    ]
                )
        except ClientError as error:
            if _is_conflict(error):
                raise ConcurrentWriteError(
                    f"{node.id!r} changed after it was read; read it again and retry"
                ) from error
            raise

    def _ids_by_type(self, node_type: NodeType) -> list[str]:
        """Node IDs from the type index. The index is eventually consistent, so a node written
        a moment ago may not be listed yet (ADR 0013)."""
        found = self._query(
            IndexName=keys.GSI1,
            KeyConditionExpression="GSI1PK = :pk",
            ExpressionAttributeValues={":pk": {"S": keys.gsi_type_pk(self.tenant, node_type)}},
        )
        return [item["GSI1SK"]["S"] for item in found]

    def nodes_by_type(self, node_type: NodeType) -> list[Node]:
        """The index holds keys only (D14), so list the IDs there, then fetch the nodes."""
        wanted = [
            {"PK": {"S": keys.node_pk(self.tenant, node_id)}, "SK": {"S": keys.META}}
            for node_id in self._ids_by_type(node_type)
        ]
        nodes = [
            items.node_from_item(item)
            for start in range(0, len(wanted), _BATCH_GET_LIMIT)
            for item in self._batch_get(wanted[start : start + _BATCH_GET_LIMIT])
        ]
        return sorted(nodes, key=lambda n: n.id)

    def _batch_get(self, wanted: list[dict[str, Any]]) -> Iterator[items.Item]:
        """`BatchGetItem` can return some keys unprocessed under load; ask again with backoff."""
        pending, attempt = wanted, 0
        while pending:
            if attempt:
                self._sleep(min(0.05 * 2**attempt, 2.0))
            response = self._client.batch_get_item(
                RequestItems={self._table: {"Keys": pending, _KEY: True}}
            )
            yield from response.get("Responses", {}).get(self._table, [])
            pending = response.get("UnprocessedKeys", {}).get(self._table, {}).get("Keys", [])
            attempt += 1
            if pending and attempt >= _BATCH_GET_ATTEMPTS:
                raise RepositoryError(f"{len(pending)} nodes were still unprocessed after retries")

    def history(self, node_id: str) -> list[Node]:
        versions = [items.node_from_item(i) for i in self._partition(node_id, "H#")]
        if versions:
            return versions
        # Evidence never changes, so it has no `H#` items: its only version is the node itself.
        node = self.get_node(node_id)
        return [node] if isinstance(node, Evidence) else []

    # --- edges ---------------------------------------------------------------------------

    def neighbors(
        self,
        node_id: str,
        direction: Direction,
        edge_type: EdgeType | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[Edge]:
        if as_of is not None and as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        prefix = (
            keys.edge_prefix(edge_type)
            if direction is Direction.OUT
            else keys.reverse_prefix(edge_type)
        )
        edges = (items.edge_from_item(i) for i in self._partition(node_id, prefix))
        return [e for e in edges if e.is_active(as_of)]

    def _open_edges_touching(self, node: Node) -> list[Edge]:
        return self.neighbors(node.id, Direction.OUT) + self.neighbors(node.id, Direction.IN)

    def _close_edges_of(self, node: Node) -> None:
        """Close every open edge of an ended node, 50 edges to a transaction. Each chunk is
        atomic, the whole is not, but closing a closed edge changes nothing, so a failed run
        is repeated by sending the node again (ADR 0013)."""
        now = read_clock(self._clock)
        pending = []
        for edge, valid_to in edges_to_close(node, self._open_edges_touching(node)):
            plan = plan_close_edge(edge, valid_to, now)
            if plan.action is not WriteAction.NOOP:
                pending.append((plan.edge, edge.version))
        self._write_edges(pending)

    def upsert_edge(self, edge: Edge) -> Edge:
        ensure_tenant(self.tenant, edge.tenant, f"{edge.type} edge")
        forward_key = (keys.node_pk(self.tenant, edge.src), keys.edge_sk(edge.key))
        # The two nodes and the stored edge, in one call.
        found = self._read(
            (keys.node_pk(self.tenant, edge.src), keys.META),
            (keys.node_pk(self.tenant, edge.dst), keys.META),
            forward_key,
        )
        src, dst, stored = (
            found.get(k)
            for k in (
                (keys.node_pk(self.tenant, edge.src), keys.META),
                (keys.node_pk(self.tenant, edge.dst), keys.META),
                forward_key,
            )
        )
        validate_edge(
            edge,
            items.node_from_item(src) if src else None,
            items.node_from_item(dst) if dst else None,
            # Only the types that limit an edge per source look at the source's other edges.
            open_out_edges=(
                self.neighbors(edge.src, Direction.OUT)
                if EDGE_RULES[edge.type].max_out is not None
                else []
            ),
        )
        existing = items.edge_from_item(stored) if stored else None
        plan = plan_edge_write(existing, edge, read_clock(self._clock))
        if plan.action is not WriteAction.NOOP:
            self._write_edges([(plan.edge, existing.version if existing else None)])
        return plan.edge

    def close_edge(
        self,
        src: str,
        edge_type: EdgeType,
        dst: str,
        *,
        valid_to: datetime,
        qualifier: str | None = None,
    ) -> Edge:
        require_aware(valid_to, "valid_to must be timezone-aware")
        key = EdgeKey(src, edge_type, dst, qualifier)
        item = self._get_item(keys.node_pk(self.tenant, src), keys.edge_sk(key))
        if item is None:
            raise EdgeNotFoundError(f"no {edge_type} edge from {src!r} to {dst!r} ({qualifier})")
        existing = items.edge_from_item(item)
        plan = plan_close_edge(existing, valid_to, read_clock(self._clock))
        if plan.action is not WriteAction.NOOP:
            self._write_edges([(plan.edge, existing.version)])
        return plan.edge

    def _read(self, *wanted: tuple[str, str]) -> dict[tuple[str, str], items.Item]:
        """Several items in one call, by (PK, SK). Missing ones are simply absent."""
        found = self._batch_get([{"PK": {"S": pk}, "SK": {"S": sk}} for pk, sk in wanted])
        return {(i["PK"]["S"], i["SK"]["S"]): i for i in found}

    def _write_edges(self, edges: list[tuple[Edge, int | None]]) -> None:
        """Write each edge as its `E#` item and `R#` mirror in one transaction, so the forward
        and reverse lookups cannot disagree. Each edge is checked against the version it was
        read at (`None` means it must not exist yet). Edges go 50 to a transaction."""
        for start in range(0, len(edges), _EDGES_PER_TRANSACTION):
            actions = []
            for edge, expected_version in edges[start : start + _EDGES_PER_TRANSACTION]:
                condition = (
                    {"ConditionExpression": "attribute_not_exists(PK)"}
                    if expected_version is None
                    else {
                        "ConditionExpression": "ver = :expected",
                        "ExpressionAttributeValues": {":expected": {"N": str(expected_version)}},
                    }
                )
                actions += [
                    {"Put": {"TableName": self._table, "Item": item, **condition}}
                    for item in items.edge_items(edge)
                ]
            try:
                self._transact(actions)
            except ClientError as error:
                if _is_conflict(error):
                    raise ConcurrentWriteError(
                        "an edge changed after it was read; read it again and retry"
                    ) from error
                raise

    # --- load the whole graph ------------------------------------------------------------

    def load_graph(self, *, as_of: datetime | None = None) -> nx.MultiDiGraph:
        """One consistent scan of the tenant's items, paged. With `as_of`, each node is the
        version the graph held then, read from its `H#` items (ADR 0012).

        A scan reads every item in the table, including the `R#` mirrors and usage records it
        then ignores, and it is not a snapshot: a node written while it runs may appear in an
        older version. Run it when no writer is active, as the daily crawl and the export are.
        """
        if as_of is not None:
            require_aware(as_of, "as_of must be timezone-aware")
        current: dict[str, Node] = {}
        versions: dict[str, list[Node]] = {}
        edges: list[Edge] = []
        for item in self._scan_tenant():
            kind = keys.kind_of(item["SK"]["S"])
            if kind == "META":
                node = items.node_from_item(item)
                current[node.id] = node
            elif kind == "H" and as_of is not None:
                node = items.node_from_item(item)
                versions.setdefault(node.id, []).append(node)
            elif kind == "E":
                edges.append(items.edge_from_item(item))
        if as_of is None:
            return build_graph(current.values(), edges)
        # Evidence never changes, so it has no `H#` items and is its own only version.
        nodes = [
            version_at(sorted(versions.get(node_id) or [node], key=lambda n: n.version), as_of)
            for node_id, node in current.items()
        ]
        return build_graph(nodes, edges, as_of=as_of)

    def _scan_tenant(self) -> Iterator[items.Item]:
        start: dict[str, Any] | None = None
        while True:
            page = self._client.scan(
                TableName=self._table,
                FilterExpression="begins_with(PK, :tenant)",
                ExpressionAttributeValues={":tenant": {"S": keys.tenant_prefix(self.tenant)}},
                ConsistentRead=True,
                Limit=self._scan_page_items,
                **({"ExclusiveStartKey": start} if start else {}),
            )
            yield from page.get("Items", [])
            start = page.get("LastEvaluatedKey")
            if not start:
                return

    # --- usage ---------------------------------------------------------------------------

    def append_usage(self, record: UsageRecord) -> None:
        self._usage.append_usage(record)

    def usage_records(
        self,
        system_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[UsageRecord]:
        check_usage_bounds(since, until)
        if since is not None and until is not None and until <= since:
            return []  # an empty interval; DynamoDB would reject a BETWEEN that runs backwards
        low, high = keys.usage_sk_range(since, until)
        found = self._query(
            KeyConditionExpression="PK = :pk AND SK BETWEEN :low AND :high",
            ExpressionAttributeValues={
                ":pk": {"S": keys.usage_pk(self.tenant, system_id)},
                ":low": {"S": low},
                ":high": {"S": high},
            },
            ConsistentRead=True,
        )
        return [items.usage_from_item(item) for item in found]


def _reads_edges(node: Node) -> bool:
    """`validate_node_change` looks at a node's open edges only for these types, so the other
    16 skip two queries per write. A test pins that assumption."""
    return node.type in (NodeType.MODEL, NodeType.AWS_RESOURCE)
