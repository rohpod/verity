"""Turns the graph into publishable records (ADR 0029, decisions 3 to 6).

1. Keep only the public fields of each record.
2. Replace account digests: the owner's becomes `000000000000`, any other an ordinal.
3. Withhold the config hash keys inside Evidence content.
4. Rebuild each Evidence whose subject or content changed, through `Evidence.build`, because its
   `sha256` and ID are computed from them. Every old ID is carried through one map.
5. Check nothing that resolved before is left dangling.

Nothing here decides what is safe to publish: `scan.py` does, from scratch.
"""

import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from verity_core.discovery.boundary import UNKNOWN_ACCOUNT, own_account
from verity_core.export.fields import WITHHELD_CONTENT_KEYS, public_fields
from verity_core.model.edges import Edge
from verity_core.model.enums import NodeType
from verity_core.model.nodes import Evidence, Node

OWN_ACCOUNT = "000000000000"
_DIGEST = re.compile(r"acct_[0-9a-f]{8}")
_EVIDENCE_ID = re.compile(r"ev:[0-9a-f]{32}")


class RedactionError(ValueError):
    """Redaction could not keep the snapshot consistent. The message holds no value."""


@dataclass(frozen=True)
class _Role:
    arn: str


@dataclass(frozen=True)
class RedactionReport:
    """Counts only, for the snapshot header and the CLI."""

    own_account_found: bool
    external_accounts: int
    content_keys_withheld: int
    evidence_rebuilt: int
    evidence_unchanged: int


@dataclass(frozen=True)
class Redacted:
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    extras: dict[str, list[dict[str, Any]]]  # the derived rows, redacted the same way
    report: RedactionReport
    # Every sha256 and ID that redaction replaced. The scanner refuses these anywhere in the file.
    replaced_hashes: frozenset[str] = field(default_factory=frozenset)
    evidence_ids: dict[str, str] = field(default_factory=dict)  # old ID -> new ID


# --- walking -----------------------------------------------------------------------------


def _strings(value: Any) -> Iterator[str]:
    """Every key and string value, depth first, keys in sorted order."""
    if isinstance(value, dict):
        for key in sorted(value):
            yield str(key)
            yield from _strings(value[key])
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


def _transform(value: Any, text: Callable[[str], str], drop: frozenset[str] = frozenset()) -> Any:
    """A copy of `value` with `text` applied to every key and string, and `drop` keys removed."""
    if isinstance(value, dict):
        return {text(k): _transform(v, text, drop) for k, v in value.items() if k not in drop}
    if isinstance(value, list):
        return [_transform(v, text, drop) for v in value]
    return text(value) if isinstance(value, str) else value


def _count_keys(value: Any, keys: frozenset[str]) -> int:
    if isinstance(value, dict):
        return sum((k in keys) + _count_keys(v, keys) for k, v in value.items())
    if isinstance(value, list):
        return sum(_count_keys(v, keys) for v in value)
    return 0


# --- accounts ----------------------------------------------------------------------------


def _own_digest(evidence: list[Evidence]) -> str | None:
    """The digest in a function's role ARN, which is always in the owner's account."""
    for item in evidence:
        config = (item.content or {}).get("config")
        role = config.get("role") if isinstance(config, dict) else None
        if isinstance(role, str):
            found = own_account([_Role(role)])
            if found != UNKNOWN_ACCOUNT:
                return found
    return None


def _account_map(records: list[dict[str, Any]], own: str | None) -> dict[str, str]:
    """The owner's digest to `000000000000`, any other to `acct_1`, `acct_2` in order of first
    appearance. `records` are in sorted order, so the same graph gives the same map."""
    mapping: dict[str, str] = {}
    if own is not None:
        mapping[own] = OWN_ACCOUNT
    for record in records:
        for text in _strings(record):
            for digest in _DIGEST.findall(text):
                if digest not in mapping:
                    mapping[digest] = f"acct_{len(mapping) - (own is not None) + 1}"
    return mapping


# --- the pass ----------------------------------------------------------------------------


def _public(record: Node | Edge) -> dict[str, Any]:
    return record.model_dump(mode="json", include=set(public_fields(type(record))))


def _references(nodes: list[dict[str, Any]]) -> dict[str, bool]:
    """Whether each reference held in a node field resolves to a node in the list, by the
    node's position, which redaction does not change."""
    ids = {n["id"] for n in nodes}
    found = {}
    for position, node in enumerate(nodes):
        if node["type"] == NodeType.EVIDENCE.value:
            found[f"{position}#subject"] = node["subject"] in ids
        if node["type"] == NodeType.CONTROL_ASSESSMENT.value and node.get("assessor"):
            found[f"{position}#assessor"] = node["assessor"] in ids
    return found


def redact(
    graph: nx.MultiDiGraph, extras: Mapping[str, list[dict[str, Any]]] | None = None
) -> Redacted:
    """`extras` are derived rows that name nodes and Evidence, such as findings and obligations.
    They go through the same account map and the same ID map as the records."""
    extras = extras or {}
    originals: list[Node] = [graph.nodes[n]["record"] for n in sorted(graph.nodes)]
    edge_records: list[Edge] = sorted(
        (data["record"] for _, _, data in graph.edges(data=True)),
        key=lambda e: (e.src, e.type.value, e.dst, e.qualifier or ""),
    )
    evidence = [n for n in originals if isinstance(n, Evidence)]

    nodes = [_public(n) for n in originals]
    edges = [_public(e) for e in edge_records]
    own = _own_digest(evidence)
    extra_rows = [row for name in sorted(extras) for row in extras[name]]
    accounts = _account_map([*nodes, *edges, *extra_rows], own)

    def text(value: str) -> str:
        return _DIGEST.sub(lambda m: accounts[m.group()], value)

    refs_before = _references(nodes)

    # Evidence whose subject or content changes is rebuilt, and gets a new sha256 and ID.
    id_map: dict[str, str] = {}
    replaced: set[str] = set()
    withheld = rebuilt = 0
    redacted_nodes: list[dict[str, Any]] = []
    for original, node in zip(originals, nodes, strict=True):
        if not isinstance(original, Evidence):
            redacted_nodes.append(_transform(node, text))
            continue
        content = original.content
        new_content = None if content is None else _transform(content, text, WITHHELD_CONTENT_KEYS)
        withheld += 0 if content is None else _count_keys(content, WITHHELD_CONTENT_KEYS)
        subject = text(original.subject)
        if new_content == content and subject == original.subject:
            redacted_nodes.append({**_transform(node, text), "redacted": False})
            continue
        rebuilt += 1
        fresh = Evidence.build(
            subject=subject,
            collector=original.collector,
            collected_at=original.collected_at,
            content=new_content,
            content_ref=original.content_ref,
            file_sha256=original.sha256 if original.content_ref is not None else None,
            kind=original.kind,
            valid_until=original.valid_until,
            tenant=original.tenant,
            source=original.source,
            confidence=original.confidence,
            valid_from=original.valid_from,
            valid_to=original.valid_to,
        )
        id_map[original.id] = fresh.id
        replaced |= {original.id, original.sha256}
        redacted_nodes.append({**_transform(_public(fresh), text), "redacted": True})

    if len(set(id_map.values())) != len(id_map):
        raise RedactionError("two Evidence items became identical after redaction")

    # One map for every reference: edges, subjects, and anything that holds an Evidence ID.

    def follow(value: str) -> str:
        return _EVIDENCE_ID.sub(lambda m: id_map.get(m.group(), m.group()), value)

    final_nodes = [_transform(n, follow) for n in redacted_nodes]
    final_edges = [_transform(_transform(e, text), follow) for e in edges]
    final_extras = {
        name: [_transform(_transform(row, text), follow) for row in rows]
        for name, rows in extras.items()
    }

    ids_after = {n["id"] for n in final_nodes}
    if len(ids_after) != len(final_nodes):
        raise RedactionError("two records share an ID after redaction")
    for edge in final_edges:
        if edge["src"] not in ids_after or edge["dst"] not in ids_after:
            raise RedactionError("an edge has no endpoint after redaction")
    refs_after = _references(final_nodes)
    lost = [k for k, ok in refs_before.items() if ok and not refs_after.get(k)]
    if lost:
        raise RedactionError(f"{len(lost)} reference(s) no longer resolve after redaction")

    for text_ in _strings([final_nodes, final_edges, *final_extras.values()]):
        if any(old in text_ for old in id_map):
            raise RedactionError("a replaced Evidence ID is still in the output")

    final_nodes.sort(key=lambda n: n["id"])
    final_edges.sort(key=lambda e: (e["src"], e["type"], e["dst"], _qualifier(e)))
    report = RedactionReport(
        own_account_found=own is not None,
        external_accounts=len(accounts) - (own is not None),
        content_keys_withheld=withheld,
        evidence_rebuilt=rebuilt,
        evidence_unchanged=len(evidence) - rebuilt,
    )
    return Redacted(final_nodes, final_edges, final_extras, report, frozenset(replaced), id_map)


def _qualifier(edge: dict[str, Any]) -> str:
    return str(edge.get("role") or edge.get("purpose") or "")
