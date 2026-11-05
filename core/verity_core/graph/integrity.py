"""Tier 3 of edge rejection (ADR 0012): problems that are legal while a graph is being loaded
but wrong once it is at rest, so no single write can be refused for them."""

from dataclasses import dataclass

import networkx as nx

from verity_core.graph.loader import in_edges, node_record, out_edges
from verity_core.model.enums import (
    SCOPE_NODE_TYPE,
    AssuranceLevel,
    EdgeType,
    ModelOrigin,
    NodeType,
)
from verity_core.model.nodes import Control, ControlAssessment, Evidence, Model


@dataclass(frozen=True)
class IntegrityIssue:
    code: str
    node_id: str
    message: str


def check_integrity(graph: nx.MultiDiGraph) -> list[IntegrityIssue]:
    """Every issue found, ordered by node ID. An empty list means the graph is sound."""
    issues: list[IntegrityIssue] = []
    for node_id in sorted(graph.nodes):
        node = node_record(graph, node_id)
        if isinstance(node, Model):
            issues += _check_model(graph, node)
        elif isinstance(node, ControlAssessment):
            issues += _check_assessment(graph, node)
        elif isinstance(node, Evidence):
            issues += _check_evidence(graph, node)
    issues += _check_requirement_cycles(graph)
    return sorted(issues, key=lambda i: (i.node_id, i.code))


def _check_model(graph: nx.MultiDiGraph, model: Model) -> list[IntegrityIssue]:
    if model.origin is ModelOrigin.THIRD_PARTY and not out_edges(
        graph, model.id, EdgeType.PROVIDED_BY
    ):
        return [IntegrityIssue("third_party_model_without_provider", model.id, "no PROVIDED_BY")]
    return []


def _check_assessment(graph: nx.MultiDiGraph, ca: ControlAssessment) -> list[IntegrityIssue]:
    issues: list[IntegrityIssue] = []
    controls = out_edges(graph, ca.id, EdgeType.ASSESSES)
    scopes = out_edges(graph, ca.id, EdgeType.SCOPED_TO)
    if not controls:
        issues.append(IntegrityIssue("assessment_without_control", ca.id, "no ASSESSES"))
    if not scopes:
        issues.append(IntegrityIssue("assessment_without_scope", ca.id, "no SCOPED_TO"))
    if controls and scopes:
        control = node_record(graph, controls[0].dst)
        scope = node_record(graph, scopes[0].dst)
        if isinstance(control, Control) and scope is not None:
            expected = SCOPE_NODE_TYPE[control.scope_level]
            if scope.type is not expected:
                issues.append(
                    IntegrityIssue(
                        "scope_level_mismatch",
                        ca.id,
                        f"{control.id} is {control.scope_level}-level but is scoped to a "
                        f"{scope.type}",
                    )
                )
    if ca.assurance_level is AssuranceLevel.L4_VERIFIED and not any(
        e.src == ca.assessor for e in in_edges(graph, ca.id, EdgeType.ASSESSED)
    ):
        issues.append(
            IntegrityIssue("l4_without_assessed_edge", ca.id, f"no ASSESSED from {ca.assessor}")
        )
    return issues


def _check_evidence(graph: nx.MultiDiGraph, evidence: Evidence) -> list[IntegrityIssue]:
    if not any(e.dst == evidence.subject for e in out_edges(graph, evidence.id, EdgeType.ABOUT)):
        return [
            IntegrityIssue(
                "evidence_not_about_subject", evidence.id, f"no ABOUT edge to {evidence.subject}"
            )
        ]
    return []


def _check_requirement_cycles(graph: nx.MultiDiGraph) -> list[IntegrityIssue]:
    hierarchy = nx.DiGraph()
    for node_id in graph.nodes:
        node = node_record(graph, node_id)
        if node is not None and node.type is NodeType.REQUIREMENT:
            for edge in out_edges(graph, node_id, EdgeType.PART_OF):
                if edge.dst in graph and node_record(graph, edge.dst).type is NodeType.REQUIREMENT:
                    hierarchy.add_edge(edge.src, edge.dst)
    return [
        IntegrityIssue(
            "part_of_cycle", min(cycle), "requirements form a cycle: " + ", ".join(sorted(cycle))
        )
        for cycle in nx.strongly_connected_components(hierarchy)
        if len(cycle) > 1
    ]
