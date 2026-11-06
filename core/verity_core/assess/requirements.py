"""Whether a requirement is satisfied for a system (architecture section F, ADR 0019). The
numbered comments below are the rows of the table there.

Built on `obligations_for`, which resolves whose assessment answers each control (the system,
the organisation or a provider, D13). This module does not copy that resolution. It takes each
row's control and resolution, finds the scope (`DIRECT` is the system, `INHERITED_ORG` the
organisation, `INHERITED_PROVIDER` the row's provider), and asks the `ControlAssessor` for that
control and scope, so nothing has to be stored first.

A requirement that applies to the organisation is evaluated for each system, because a control
mapped to it may be assessed at system level.
"""

from dataclasses import dataclass
from enum import StrEnum

import networkx as nx

from verity_core.assess.controls import ControlAssessor, ControlResult
from verity_core.graph.loader import in_edges, node_record, out_edges
from verity_core.graph.traversals import Resolution, _organisation, obligations_for
from verity_core.model.edges import AppliesToEdge
from verity_core.model.enums import AssuranceLevel, EdgeType, Source, StrmType, Sufficiency
from verity_core.model.nodes import Control
from verity_core.rules.status import ApplicabilityStatus, applicability_status


class RequirementState(StrEnum):
    SATISFIED = "satisfied"
    PARTIALLY_ADDRESSED = "partially_addressed"
    NOT_MET = "not_met"
    NOT_ADDRESSED = "not_addressed"
    NOT_APPLICABLE = "not_applicable"


# Why a state is what it is, where the state alone does not say.
IN_HOUSE_ONLY = "in_house_only"
ROLLUP = "rollup"
NEVER_MAPPED = "never_mapped"
REVIEWED_NO_CONTROL = "reviewed_no_control"
AUTOMATED_ONLY = "automated_only"
PARTIAL_ONLY = "partial_only"

_STRENGTH = (
    ApplicabilityStatus.IN_FORCE,
    ApplicabilityStatus.CONDITIONAL,
    ApplicabilityStatus.UPCOMING,
)


@dataclass(frozen=True)
class Target:
    """One control and the scope whose assessment answers it. `scope_id` is None when no one
    can be asked, which is `provider_unknown`."""

    control_id: str
    scope_id: str | None
    resolution: Resolution


@dataclass(frozen=True)
class RequirementStatus:
    requirement_id: str
    system_id: str
    state: RequirementState
    reason: str | None
    targets: tuple[Target, ...]
    applicability: ApplicabilityStatus | None  # the strongest of its APPLIES_TO edges
    # Whether a met control (or, for a parent, a child) rests on a simulated sign-off. A demo
    # result must never look like a real one (CLAUDE.md, honesty rules).
    simulated: bool = False


def requirement_statuses(
    graph: nx.MultiDiGraph, system_id: str, assessor: ControlAssessor
) -> list[RequirementStatus]:
    """The status of every requirement that applies to the system or its organisation."""
    rows = obligations_for(graph, system_id)
    by_requirement: dict[str, list] = {}
    for row in rows:
        by_requirement.setdefault(row.requirement_id, []).append(row)
    organisation = _organisation(graph)
    cache: dict[str, RequirementStatus] = {}

    def evaluate(requirement_id: str) -> RequirementStatus:
        if requirement_id not in cache:
            cache[requirement_id] = _evaluate(
                graph,
                system_id,
                organisation.id if organisation else None,
                requirement_id,
                by_requirement[requirement_id],
                assessor,
                evaluate_child=lambda child: evaluate(child) if child in by_requirement else None,
            )
        return cache[requirement_id]

    return [evaluate(r) for r in sorted(by_requirement)]


def _evaluate(
    graph, system_id, organisation_id, requirement_id, rows, assessor, evaluate_child
) -> RequirementStatus:
    applicability = _applicability(graph, requirement_id, system_id, organisation_id, assessor)

    def status(state, reason=None, targets=(), simulated=False) -> RequirementStatus:
        return RequirementStatus(
            requirement_id, system_id, state, reason, tuple(targets), applicability, simulated
        )

    if all(r.resolution is Resolution.NOT_APPLICABLE for r in rows):  # 1
        return status(RequirementState.NOT_APPLICABLE, IN_HOUSE_ONLY)

    mappings = [
        e for e in out_edges(graph, requirement_id, EdgeType.MAPS_TO) if e.type is EdgeType.MAPS_TO
    ]
    children = [
        e.src for e in in_edges(graph, requirement_id, EdgeType.PART_OF) if e.src.startswith("req:")
    ]
    if children and not mappings:  # 2: a parent is never Satisfied from its children
        done = [evaluate_child(c) for c in sorted(children)]
        addressed = {RequirementState.SATISFIED, RequirementState.PARTIALLY_ADDRESSED}
        counted = [c for c in done if c is not None and c.state in addressed]
        if counted:
            return status(
                RequirementState.PARTIALLY_ADDRESSED,
                ROLLUP,
                simulated=any(c.simulated for c in counted),
            )
        return status(RequirementState.NOT_MET, ROLLUP)

    if all(r.control_id is None for r in rows):  # 3
        reviewed = any(m.strm is StrmType.NO_RELATIONSHIP for m in mappings)
        return status(
            RequirementState.NOT_ADDRESSED, REVIEWED_NO_CONTROL if reviewed else NEVER_MAPPED
        )

    # Group the rows by control. A control is met if every target it resolves to is met.
    targets: dict[str, list[Target]] = {}
    mapping_of = {}
    for row in rows:
        if row.control_id is None or row.resolution is Resolution.NOT_APPLICABLE:
            continue
        scope = {
            Resolution.DIRECT: system_id,
            Resolution.INHERITED_ORG: organisation_id,
            Resolution.INHERITED_PROVIDER: row.provider_id,
        }.get(row.resolution)
        target = Target(row.control_id, scope, row.resolution)
        if target not in targets.setdefault(row.control_id, []):
            targets[row.control_id].append(target)
        mapping_of[row.control_id] = row.mapping
    all_targets = [t for ts in targets.values() for t in ts]

    def results(control_id: str) -> list[ControlResult | None]:
        return [
            assessor.assess(t.control_id, t.scope_id) if t.scope_id is not None else None
            for t in targets[control_id]
        ]

    def met(control_id: str) -> bool:
        found = results(control_id)
        return bool(found) and all(r is not None and r.met for r in found)

    def verified(control_id: str) -> bool:
        found = results(control_id)
        return all(r is not None and r.level is AssuranceLevel.L4_VERIFIED for r in found)

    def automatable(control_id: str) -> bool:
        control = node_record(graph, control_id)
        return not isinstance(control, Control) or control.automatable

    def simulated() -> bool:
        return any(
            r is not None and r.met and r.source is Source.SIMULATED
            for c in targets
            for r in results(c)
        )

    full = [c for c in targets if mapping_of[c].sufficiency is Sufficiency.FULL]
    if full and all(met(c) for c in full):
        # Automated checks alone never satisfy a requirement (ADR 0019, decision 1).
        if any(not automatable(c) or verified(c) for c in full):  # 4
            return status(RequirementState.SATISFIED, None, all_targets, simulated())
        return status(
            RequirementState.PARTIALLY_ADDRESSED, AUTOMATED_ONLY, all_targets, simulated()
        )  # 5
    if any(met(c) for c in targets):  # 6
        return status(RequirementState.PARTIALLY_ADDRESSED, PARTIAL_ONLY, all_targets, simulated())
    return status(RequirementState.NOT_MET, None, all_targets)  # 7


def _applicability(graph, requirement_id, system_id, organisation_id, assessor):
    found = {
        applicability_status(e, assessor.as_of)
        for aim in (system_id, organisation_id)
        if aim is not None
        for e in in_edges(graph, aim, EdgeType.APPLIES_TO)
        if isinstance(e, AppliesToEdge) and e.src == requirement_id
    }
    return next((s for s in _STRENGTH if s in found), None)
