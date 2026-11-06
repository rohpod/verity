"""Turns the graph into publishable records (ADR 0029, decisions 3 to 6).

1. Keep only the public fields of each record, the listed tags and the listed content keys.
2. Replace account digests: the owner's becomes `000000000000`, any other an ordinal.
3. Withhold the config hash keys inside Evidence content.
4. Rebuild each Evidence whose subject or content changed, through `Evidence.build`, because its
   `sha256` and ID are computed from them. Every old ID is carried through one map.
5. Check nothing that resolved before is left dangling, and every published hash still verifies.

Nothing here decides what is safe to publish: `scan.py` does, from scratch.
"""

import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from verity_core.discovery.boundary import UNKNOWN_ACCOUNT, own_account
from verity_core.export.fields import (
    PUBLIC_CONFIG_KEYS,
    PUBLIC_CONTENT_KEYS,
    PUBLIC_POLICY_KEYS,
    PUBLIC_STATEMENT_KEYS,
    PUBLIC_TAG_KEYS,
    PUBLIC_TRUST_KEYS,
    WITHHELD_CONTENT_KEYS,
    public_fields,
)
from verity_core.model.edges import Edge
from verity_core.model.enums import NodeType
from verity_core.model.evidence import content_sha256
from verity_core.model.nodes import AWSResource, ChangeEvent, Evidence, Node

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
    tags_withheld: int
    evidence_rebuilt: int
    evidence_unchanged: int


@dataclass(frozen=True)
class Redacted:
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    extras: dict[str, list[dict[str, Any]]]  # the derived rows, redacted the same way
    report: RedactionReport
    # Every sha256 and ID that redaction replaced, and every config hash it withheld. The scanner
    # refuses these anywhere in the file.
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
    """The digest in the functions' role ARNs. A function's role is always in its own account, so
    two digests mean the graph is not what it seems: a guess could label another account as the
    owner's, so it is refused."""
    found = set()
    for item in evidence:
        config = (item.content or {}).get("config")
        role = config.get("role") if isinstance(config, dict) else None
        if isinstance(role, str):
            found.add(own_account([_Role(role)]))
    found.discard(UNKNOWN_ACCOUNT)
    if len(found) > 1:
        raise RedactionError("function roles name more than one account")
    return found.pop() if found else None


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


# --- listed content and tags -------------------------------------------------------------


def _unlisted(value: Any, listed: frozenset[str]) -> int:
    return len(set(value) - listed - WITHHELD_CONTENT_KEYS) if isinstance(value, dict) else 0


def _unlisted_content_keys(item: Evidence) -> int:
    """Keys of Evidence content that are neither public nor withheld (ADR 0030)."""
    content = item.content or {}
    count = _unlisted(content, PUBLIC_CONTENT_KEYS[item.kind])
    config = content.get("config")
    if not isinstance(config, dict):
        return count
    count += _unlisted(config, PUBLIC_CONFIG_KEYS)
    for policy in config.get("policies") or []:
        count += _unlisted(policy, PUBLIC_POLICY_KEYS)
        count += sum(_unlisted(s, PUBLIC_STATEMENT_KEYS) for s in policy.get("statements") or [])
    return count + sum(_unlisted(t, PUBLIC_TRUST_KEYS) for t in config.get("trust") or [])


def _listed_tags(tags: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in tags.items() if key in PUBLIC_TAG_KEYS}


def _without_unlisted_tags(content: dict[str, Any]) -> dict[str, Any]:
    config = content.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("tags"), dict):
        return content
    return {**content, "config": {**config, "tags": _listed_tags(config["tags"])}}


def _withheld_hashes(record: Node) -> set[str]:
    """The config hashes a record holds. None is published, and the scanner is told so."""
    if isinstance(record, AWSResource):
        found = {record.config_hash}
    elif isinstance(record, ChangeEvent):
        found = {record.previous_config_hash, record.new_config_hash}
    elif isinstance(record, Evidence):
        found = {(record.content or {}).get("config_hash")}
    else:
        return set()
    return {value for value in found if isinstance(value, str)}


# --- the pass ----------------------------------------------------------------------------


def _public(record: Node | Edge) -> dict[str, Any]:
    dumped = record.model_dump(mode="json", include=set(public_fields(type(record))))
    if isinstance(record, AWSResource):
        dumped["tags"] = _listed_tags(dumped["tags"])
    return dumped


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
    unlisted = sum(_unlisted_content_keys(item) for item in evidence)
    if unlisted:
        raise RedactionError(f"{unlisted} Evidence content key(s) are not listed as public")

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
    replaced: set[str] = {value for record in originals for value in _withheld_hashes(record)}
    withheld = rebuilt = 0
    tags_withheld = sum(
        len(n.tags) - len(_listed_tags(n.tags)) for n in originals if isinstance(n, AWSResource)
    )
    redacted_nodes: list[dict[str, Any]] = []
    for original, node in zip(originals, nodes, strict=True):
        if not isinstance(original, Evidence):
            redacted_nodes.append(_transform(node, text))
            continue
        content = original.content
        new_content = (
            None
            if content is None
            else _transform(_without_unlisted_tags(content), text, WITHHELD_CONTENT_KEYS)
        )
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
        replaced.add(original.id)
        if content is not None:  # the hash of a `content_ref` file holds no account, and stays
            replaced.add(original.sha256)
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

    for node in final_nodes:
        is_inline = node["type"] == NodeType.EVIDENCE.value and node.get("content") is not None
        if is_inline and content_sha256(node["content"]) != node["sha256"]:
            raise RedactionError("a published Evidence hash does not match its content")

    final_nodes.sort(key=lambda n: n["id"])
    final_edges.sort(key=lambda e: (e["src"], e["type"], e["dst"], _qualifier(e)))
    report = RedactionReport(
        own_account_found=own is not None,
        external_accounts=len(accounts) - (own is not None),
        content_keys_withheld=withheld,
        tags_withheld=tags_withheld,
        evidence_rebuilt=rebuilt,
        evidence_unchanged=len(evidence) - rebuilt,
    )
    return Redacted(final_nodes, final_edges, final_extras, report, frozenset(replaced), id_map)


def _qualifier(edge: dict[str, Any]) -> str:
    return str(edge.get("role") or edge.get("purpose") or "")
