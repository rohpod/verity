"""The rows the dashboard cannot compute itself (ADR 0029, decision 10).

The five traversals are Python, and rewriting them in TypeScript would make a second
implementation that can drift. So they run here, once, on the graph, and the file carries the
answers: obligations per system, provider impact per provider and the crosswalk per pair of
frameworks. Findings, requirement statuses and control results come from the same assessment run
(decision 2). Audit trails and `stale_by_change` follow edges, so the dashboard reads them from
`edges`; `H#` history and `U#` usage records stay out.

Nothing is reimplemented: each row is a traversal's own output, in the snapshot's shape.
"""

from typing import Any

import networkx as nx

from verity_core.assess.apply import ApplyResult
from verity_core.export.snapshot import (
    SnapshotControlResult,
    SnapshotCrosswalk,
    SnapshotCrosswalkLink,
    SnapshotFinding,
    SnapshotObligation,
    SnapshotProviderImpact,
    SnapshotRequirementStatus,
    SnapshotSystemImpact,
    SnapshotTarget,
)
from verity_core.graph.traversals import (
    crosswalk,
    frameworks_of,
    obligations_for,
    provider_impact,
)
from verity_core.model.enums import NodeType, Source


def _ids_of(graph: nx.MultiDiGraph, node_type: NodeType) -> list[str]:
    return [n for n in sorted(graph.nodes) if graph.nodes[n]["record"].type is node_type]


def _dump(rows: list[Any]) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in rows]


def findings(result: ApplyResult) -> list[dict[str, Any]]:
    simulated = {(r.control_id, r.scope_id) for r in result.results if r.source is Source.SIMULATED}
    return _dump(
        [
            SnapshotFinding(
                code=f.code,
                severity=f.severity,
                subject=f.subject,
                message=f.message,
                control_id=f.control_id,
                simulated=(f.control_id, f.subject) in simulated,
            )
            for f in result.findings
        ]
    )


def requirement_statuses(result: ApplyResult) -> list[dict[str, Any]]:
    return _dump(
        [
            SnapshotRequirementStatus(
                requirement_id=s.requirement_id,
                system_id=s.system_id,
                state=s.state,
                reason=s.reason,
                targets=[
                    SnapshotTarget(
                        control_id=t.control_id, scope_id=t.scope_id, resolution=t.resolution
                    )
                    for t in s.targets
                ],
                applicability=s.applicability,
                simulated=s.simulated,
            )
            for s in result.statuses
        ]
    )


def control_results(result: ApplyResult) -> list[dict[str, Any]]:
    return _dump(
        [
            SnapshotControlResult(
                control_id=r.control_id,
                scope_id=r.scope_id,
                status=r.status,
                level=r.level,
                method=r.method,
                assessor=r.assessor,
                simulated=r.source is Source.SIMULATED,
                evidence_id=r.evidence_id,
                freshness=r.freshness,
            )
            for r in result.results
        ]
    )


def obligations(graph: nx.MultiDiGraph) -> list[dict[str, Any]]:
    rows = []
    for system_id in _ids_of(graph, NodeType.AI_SYSTEM):
        for row in obligations_for(graph, system_id):
            mapping = row.mapping
            rows.append(
                SnapshotObligation(
                    system_id=system_id,
                    requirement_id=row.requirement_id,
                    role=row.role,
                    applies_to=row.applies_to,
                    control_id=row.control_id,
                    strm=mapping.strm if mapping else None,
                    strength=mapping.strength if mapping else None,
                    sufficiency=mapping.sufficiency if mapping else None,
                    resolution=row.resolution,
                    provider_id=row.provider_id,
                    assessment_id=row.assessment_id,
                    evidence_ids=list(row.evidence_ids),
                )
            )
    return _dump(rows)


def provider_impacts(graph: nx.MultiDiGraph) -> list[dict[str, Any]]:
    rows = []
    for provider_id in _ids_of(graph, NodeType.PROVIDER):
        impact = provider_impact(graph, provider_id)
        rows.append(
            SnapshotProviderImpact(
                provider_id=impact.provider_id,
                assessment_ids=list(impact.assessment_ids),
                systems=[
                    SnapshotSystemImpact(
                        system_id=s.system_id,
                        model_ids=list(s.model_ids),
                        owner_ids=list(s.owner_ids),
                        risk_ids=list(s.risk_ids),
                        requirement_ids=list(s.requirement_ids),
                    )
                    for s in impact.systems
                ],
            )
        )
    return _dump(rows)


def crosswalks(graph: nx.MultiDiGraph) -> list[dict[str, Any]]:
    """Every requirement that reaches a requirement of another framework through a hub control,
    for each ordered pair of frameworks. A pair with no link has no row."""
    frameworks = _ids_of(graph, NodeType.FRAMEWORK)
    rows = []
    for requirement_id in _ids_of(graph, NodeType.REQUIREMENT):
        own = frameworks_of(graph, requirement_id)
        for source in own:
            for target in frameworks:
                if target == source or target in own:
                    continue
                links = crosswalk(graph, requirement_id, target)
                if links:
                    rows.append(
                        SnapshotCrosswalk(
                            from_framework=source,
                            to_framework=target,
                            requirement_id=requirement_id,
                            links=[
                                SnapshotCrosswalkLink(
                                    via_control_id=link.via_control_id,
                                    target_requirement_id=link.target_requirement_id,
                                    strength=link.strength,
                                    from_strm=link.left.strm,
                                    to_strm=link.right.strm,
                                )
                                for link in links
                            ],
                        )
                    )
    return _dump(rows)


def derive(graph: nx.MultiDiGraph, result: ApplyResult) -> dict[str, list[dict[str, Any]]]:
    return {
        "findings": findings(result),
        "requirement_statuses": requirement_statuses(result),
        "control_results": control_results(result),
        "obligations": obligations(graph),
        "provider_impact": provider_impacts(graph),
        "crosswalk": crosswalks(graph),
    }
