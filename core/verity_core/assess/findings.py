"""Findings, derived on read and never stored (architecture section G, ADR 0019). Sorted:
severity, then code, subject, message, so the same graph and `as_of` always give the same list.

A missing piece of evidence is high only if it backs a requirement of a binding framework that is
in force or conditional (ADR 0020). Everything else it backs is a standard Kestrel adopted.

`risk_tier_unconfirmed`, `risk_tier_expired` and `unknown_fact` come from the applicability
engine, so the caller passes them in. Everything else is derived here from the graph, the
control results and the requirement statuses.

`shadow_ai_candidate` is one per open Candidate that has no open `PROMOTED_TO` edge (ADR 0021).
"""

from collections.abc import Iterable, Sequence
from datetime import datetime

import networkx as nx

from verity_core.assess.controls import ControlResult
from verity_core.assess.freshness import Freshness
from verity_core.assess.requirements import RequirementStatus
from verity_core.graph.loader import in_edges, node_record, out_edges
from verity_core.graph.traversals import Resolution
from verity_core.model import ids
from verity_core.model.edges import AppliesToEdge
from verity_core.model.enums import AiLikelihood, EdgeType, ImplementationStatus
from verity_core.model.nodes import AISystem, Candidate, Framework
from verity_core.rules.finding import Finding, Severity
from verity_core.rules.status import ApplicabilityStatus, applicability_status

_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
_IN_SCOPE = (ApplicabilityStatus.IN_FORCE, ApplicabilityStatus.CONDITIONAL)


def _binding(graph: nx.MultiDiGraph, requirement_id: str) -> bool:
    framework = node_record(graph, ids.framework_id(requirement_id.split(":")[1]))
    return isinstance(framework, Framework) and framework.binding


def _shadow(candidate: Candidate) -> Finding:
    """Declared, confirmed and probable signs are high; a name that merely suggests AI is not."""
    severity = (
        Severity.MEDIUM if candidate.ai_likelihood is AiLikelihood.POSSIBLE else Severity.HIGH
    )
    return Finding(
        "shadow_ai_candidate",
        severity,
        candidate.id,
        f"{candidate.name} looks like AI ({candidate.ai_likelihood.value}: "
        f"{', '.join(candidate.signals)}) and is not in the registry.",
    )


def derive_findings(
    graph: nx.MultiDiGraph,
    as_of: datetime,
    results: Sequence[ControlResult],
    statuses: Sequence[RequirementStatus],
    applicability_findings: Iterable[Finding] = (),
) -> list[Finding]:
    found = list(applicability_findings)
    behind: dict[tuple[str, str], list[RequirementStatus]] = {}
    for status in statuses:
        for target in status.targets:
            if target.scope_id is not None:
                behind.setdefault((target.control_id, target.scope_id), []).append(status)

    for r in results:
        where = f"{r.control_id} for {r.scope_id}"
        if r.status is ImplementationStatus.NOT_IMPLEMENTED:
            found.append(
                Finding(
                    "control_not_met",
                    Severity.HIGH,
                    r.scope_id,
                    f"{where} is not implemented.",
                    r.control_id,
                )
            )
        if r.status is ImplementationStatus.NOT_ASSESSED:
            # High only if binding law needs it now. A standard Kestrel adopted is medium.
            in_scope = any(
                s.applicability in _IN_SCOPE and _binding(graph, s.requirement_id)
                for s in behind.get((r.control_id, r.scope_id), ())
            )
            found.append(
                Finding(
                    "no_evidence",
                    Severity.HIGH if in_scope else Severity.MEDIUM,
                    r.scope_id,
                    f"{where} has no usable evidence.",
                    r.control_id,
                )
            )
        if r.freshness is Freshness.EXPIRING:
            found.append(
                Finding(
                    "evidence_expiring",
                    Severity.LOW,
                    r.scope_id,
                    f"The evidence for {where} expires within 7 days.",
                    r.control_id,
                )
            )

    for status in statuses:
        for target in status.targets:
            if target.resolution is Resolution.PROVIDER_UNKNOWN:
                found.append(
                    Finding(
                        "provider_unknown",
                        Severity.HIGH,
                        status.system_id,
                        f"{target.control_id} needs a model provider and none is recorded "
                        f"for {status.system_id}.",
                    )
                )

    for node_id in sorted(graph.nodes):
        candidate = node_record(graph, node_id)
        if isinstance(candidate, Candidate) and not out_edges(
            graph, candidate.id, EdgeType.PROMOTED_TO
        ):
            found.append(_shadow(candidate))
        system = node_record(graph, node_id)
        if not isinstance(system, AISystem):
            continue
        if not in_edges(graph, system.id, EdgeType.OWNS):
            found.append(
                Finding("no_owner", Severity.MEDIUM, system.id, f"{system.name} has no owner.")
            )
        conditional = any(
            isinstance(e, AppliesToEdge)
            and applicability_status(e, as_of) is ApplicabilityStatus.CONDITIONAL
            for e in in_edges(graph, system.id, EdgeType.APPLIES_TO)
        )
        if conditional:
            found.append(
                Finding(
                    "conditional_obligation",
                    Severity.LOW,
                    system.id,
                    f"{system.name} has obligations that apply only after a significant change.",
                )
            )

    unique = {(f.code, f.subject, f.message): f for f in found}
    return sorted(unique.values(), key=lambda f: (_ORDER[f.severity], f.code, f.subject, f.message))
