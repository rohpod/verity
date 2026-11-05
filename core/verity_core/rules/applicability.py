"""What applies to whom: requirements to the organisation and to systems (ADR 0019).

Pure. It reads the graph, the rules and the obligation dates, and takes no clock: whether an
edge is in force is `status.py`'s job, from an `as_of` the caller supplies. Every edge is
`source=derived` and its `reason` is one plain sentence naming the rule and the fact.

High-risk is a candidate until a person decides (ADR 0008, ADR 0019). A `risk_tier` decision
confirms or rejects it, and the latest one wins. Rules apply to unconfirmed candidates.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

import networkx as nx

from verity_core.content.schema import ApplicabilityFile, ApplicabilityRule, ObligationDate
from verity_core.graph.loader import in_edges, node_record
from verity_core.model.edges import AppliesToEdge
from verity_core.model.enums import AppliesCondition, EdgeType, NodeType, Role, Source
from verity_core.model.evidence import Evidence
from verity_core.model.nodes import AISystem, Organisation
from verity_core.rules.decisions import superseded_decision_ids
from verity_core.rules.finding import Finding, Severity

HELD_ROLES = (Role.PROVIDER, Role.DEPLOYER)


class RiskTier(StrEnum):
    CONFIRMED = "confirmed"  # a person decided it is high-risk
    CANDIDATE = "candidate"  # an Annex III domain, and no decision yet
    NOT_HIGH_RISK = "not_high_risk"


@dataclass(frozen=True)
class _Tier:
    tier: RiskTier
    detail: str  # what the reason sentence says about it

    @property
    def applies(self) -> bool:
        return self.tier is not RiskTier.NOT_HIGH_RISK


def applicable_edges(
    graph: nx.MultiDiGraph,
    rules: ApplicabilityFile,
    dates: Iterable[ObligationDate],
    as_of: datetime,
) -> tuple[list[AppliesToEdge], list[Finding]]:
    """Which edges exist depends on `as_of` through the decisions in force then (ADR 0020)."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    date_of = {d.id: d.date for d in dates}
    systems = _records(graph, AISystem)
    organisation = next(iter(_records(graph, Organisation)), None)
    tiers = {s.id: _tier(graph, s, rules.annex_iii_domains, as_of) for s in systems}

    findings: dict[tuple[str, str, str], Finding] = {}
    for system in systems:
        if tiers[system.id].tier is RiskTier.CANDIDATE:
            findings[("risk_tier_unconfirmed", system.id, "")] = Finding(
                "risk_tier_unconfirmed",
                Severity.HIGH,
                system.id,
                f"{system.name} is an Annex III candidate and no person has decided its risk tier.",
            )

    def unknown(system: AISystem, fact: str) -> None:
        findings[("unknown_fact", system.id, fact)] = Finding(
            "unknown_fact",
            Severity.MEDIUM,
            system.id,
            f"{system.name} has no value for {fact}, which a rule needs.",
        )

    edges: dict[tuple, AppliesToEdge] = {}

    def add(edge: AppliesToEdge) -> None:
        edges[(edge.src, edge.dst, edge.role)] = edge

    for rule in rules.rules:
        requirement_ids = _requirements(graph, rule)
        if rule.target == "organisation":
            if organisation is None:
                continue
            starts = date_of[rule.date] if rule.date is not None else None
            for role, reason in _organisation_roles(rule, organisation, systems):
                for req in requirement_ids:
                    add(_edge(req, organisation, role, rule, reason, starts, None))
            continue
        for system in systems:
            if rule.role not in system.roles:
                continue
            facts = [(f, getattr(system, f)) for f in rule.reads]
            if any(value is None for _, value in facts):
                for fact, value in facts:
                    if value is None:
                        unknown(system, fact)
                continue
            if not all(value for _, value in facts):
                continue
            tier = tiers[system.id]
            if rule.high_risk and not tier.applies:
                continue
            in_force, condition, note = _in_force(rule, system, date_of)
            if system.first_placed_on_market is None and (rule.legacy_date or rule.art_111_2):
                unknown(system, "first_placed_on_market")
            reason = _reason(rule, system, facts, tier if rule.high_risk else None, note)
            for req in requirement_ids:
                add(_edge(req, system, rule.role, rule, reason, in_force, condition))

    ordered = sorted(edges.values(), key=lambda e: (e.src, e.dst, e.role.value))
    return ordered, sorted(findings.values(), key=lambda f: (f.code, f.subject, f.message))


def _records[T](graph: nx.MultiDiGraph, kind: type[T]) -> list[T]:
    found = (node_record(graph, n) for n in sorted(graph.nodes))
    return [n for n in found if isinstance(n, kind)]


def _requirements(graph: nx.MultiDiGraph, rule: ApplicabilityRule) -> list[str]:
    named = [r for r in rule.requirements if r in graph]
    if not rule.leaves_of:
        return named
    parents = {
        e.dst
        for n in graph.nodes
        for e in in_edges(graph, n, EdgeType.PART_OF)
        if e.src.startswith("req:") and e.dst.startswith("req:")
    }
    prefixes = tuple(f"req:{slug}:" for slug in rule.leaves_of)
    return [
        n
        for n in sorted(graph.nodes)
        if n.startswith(prefixes)
        and graph.nodes[n]["record"].type is NodeType.REQUIREMENT
        and n not in parents
    ]


def _tier(
    graph: nx.MultiDiGraph, system: AISystem, annex_iii: dict[str, str], as_of: datetime
) -> _Tier:
    about = [node_record(graph, e.src) for e in in_edges(graph, system.id, EdgeType.ABOUT)]
    about = [d for d in about if isinstance(d, Evidence)]
    superseded = superseded_decision_ids(about, as_of)
    decided = [
        d
        for d in about
        if (d.content or {}).get("decision_kind") == "risk_tier"
        and (d.content or {})["decision_id"] not in superseded
        and d.collected_at <= as_of
    ]
    if decided:
        latest = max(decided, key=lambda d: (d.collected_at, d.id))
        if latest.content["tier"] == "high_risk":
            return _Tier(
                RiskTier.CONFIRMED,
                f"confirmed high-risk by decision {latest.content['decision_id']}",
            )
        return _Tier(RiskTier.NOT_HIGH_RISK, "")
    listed = sorted(d for d in system.use_domains if d in annex_iii)
    if listed:
        return _Tier(
            RiskTier.CANDIDATE, f"a high-risk candidate ({annex_iii[listed[0]]}), not yet decided"
        )
    return _Tier(RiskTier.NOT_HIGH_RISK, "")


def _organisation_roles(
    rule: ApplicabilityRule, organisation: Organisation, systems: list[AISystem]
) -> list[tuple[Role, str]]:
    if rule.role != "held":
        return [(rule.role, f"Rule {rule.id} applies to {organisation.name} in every role.")]
    return [
        (role, f"Rule {rule.id}: {organisation.name} has a system in the {role.value} role.")
        for role in HELD_ROLES
        if any(role in s.roles for s in systems)
    ]


def _in_force(
    rule: ApplicabilityRule, system: AISystem, date_of: dict[str, date]
) -> tuple[date | None, AppliesCondition | None, str]:
    """The date the edge starts, its condition, and a sentence for the reason."""
    if rule.date is None:
        return None, None, ""
    base = date_of[rule.date]
    placed = system.first_placed_on_market
    legacy = placed is not None and placed < base
    if rule.legacy_date is not None and legacy:
        return (
            date_of[rule.legacy_date],
            None,
            f"It was first placed on the market on {placed}, before {base}, "
            "so the legacy date applies",
        )
    if rule.art_111_2 and legacy:
        change = system.significant_change_on
        if change is not None and change >= base:
            return (
                change,
                None,
                f"Its significant change on {change} brings it into scope (Art. 111(2))",
            )
        return (
            base,
            AppliesCondition.LEGACY_SIGNIFICANT_CHANGE,
            f"It was first placed on the market on {placed}, before {base}, so it is in scope "
            "only after a significant design change (Art. 111(2))",
        )
    return base, None, ""


def _reason(rule, system, facts, tier: _Tier | None, note: str) -> str:
    parts = [f"holds the {rule.role.value} role"]
    parts += [f"has {name} set to true" for name, _ in facts]
    if tier is not None:
        parts.append(f"is {tier.detail}")
    text = f"Rule {rule.id}: {system.name} {', '.join(parts)}"
    return f"{text}. {note}." if note else f"{text}."


def _edge(
    requirement: str,
    target: AISystem | Organisation,
    role: Role,
    rule: ApplicabilityRule,
    reason: str,
    in_force_from: date | None,
    condition: AppliesCondition | None,
) -> AppliesToEdge:
    return AppliesToEdge(
        src=requirement,
        dst=target.id,
        role=role,
        rule_id=rule.id,
        reason=reason,
        in_force_from=in_force_from,
        condition=condition,
        tenant=target.tenant,
        source=Source.DERIVED,
    )
