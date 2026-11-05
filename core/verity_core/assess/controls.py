"""The assessment of one control for one scope, from the evidence about it (ADR 0005 and 0019).

Usable evidence names the control in `content["control"]` and the scope in `content["scope"]`,
was collected by `as_of`, and is not stale. The first matching row of the table wins. A row for
automated evidence needs an automatable control, so the only way to make a non-automatable
control Implemented is a person's verification decision (row 2).

Pure: it reads the graph and an explicit `as_of`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import networkx as nx

from verity_core.assess.freshness import Freshness, evidence_in_graph, freshness, stale_evidence_ids
from verity_core.graph.loader import node_record
from verity_core.model.enums import (
    AssuranceLevel,
    EvidenceKind,
    ImplementationStatus,
    Source,
)
from verity_core.model.nodes import Control, Evidence

PERSON = "person:"


@dataclass(frozen=True)
class ControlResult:
    control_id: str
    scope_id: str
    status: ImplementationStatus
    level: AssuranceLevel
    method: str  # names the row of the table that decided it
    assessor: str | None  # a person ID, for a verification (L4)
    source: Source  # simulated if the deciding evidence is, otherwise derived
    evidence_id: str | None  # the deciding evidence
    freshness: Freshness | None  # of the deciding evidence

    @property
    def met(self) -> bool:
        """Implemented at L2 or above: what a requirement needs from a control."""
        return (
            self.status is ImplementationStatus.IMPLEMENTED
            and self.level >= AssuranceLevel.L2_EVIDENCED
        )


class ControlAssessor:
    """Assesses controls at one `as_of`, and remembers every result it gives."""

    def __init__(self, graph: nx.MultiDiGraph, as_of: datetime):
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        self.graph = graph
        self.as_of = as_of
        self._stale = stale_evidence_ids(graph, as_of)
        self._evidence: dict[tuple[str, str], list[Evidence]] = {}
        for ev in evidence_in_graph(graph):
            key = (ev.content or {}).get("control"), (ev.content or {}).get("scope")
            if isinstance(key[0], str) and isinstance(key[1], str):
                self._evidence.setdefault(key, []).append(ev)
        self._results: dict[tuple[str, str], ControlResult] = {}

    def assess(self, control_id: str, scope_id: str) -> ControlResult:
        key = (control_id, scope_id)
        if key not in self._results:
            control = node_record(self.graph, control_id)
            if not isinstance(control, Control):
                raise ValueError(f"{control_id!r} is not a control in the graph")
            found = self._evidence.get(key, [])
            self._results[key] = decide(control, scope_id, found, self.as_of, self._stale)
        return self._results[key]

    def results(self) -> list[ControlResult]:
        return [self._results[k] for k in sorted(self._results)]


def decide(
    control: Control,
    scope_id: str,
    evidence: Sequence[Evidence],
    as_of: datetime,
    stale_ids: frozenset[str] = frozenset(),
) -> ControlResult:
    """Apply the table to the evidence about `control` and `scope_id`."""
    usable = sorted(
        (
            e
            for e in evidence
            if e.collected_at <= as_of and freshness(e, as_of, stale_ids) is not Freshness.STALE
        ),
        key=lambda e: (e.collected_at, e.id),
        reverse=True,  # latest first
    )

    def first(kind: EvidenceKind, *, decision: str | None = None, automated=None):
        for e in usable:
            content = e.content or {}
            if e.kind is not kind:
                continue
            if decision is not None and content.get("decision_kind") != decision:
                continue
            person = e.collector.startswith(PERSON)
            if automated is not None and person == automated:
                continue
            return e
        return None

    def result(status, level, method, deciding: Evidence | None) -> ControlResult:
        simulated = deciding is not None and deciding.source is Source.SIMULATED
        return ControlResult(
            control_id=control.id,
            scope_id=scope_id,
            status=status,
            level=level,
            method=method,
            assessor=deciding.collector
            if level is AssuranceLevel.L4_VERIFIED and deciding
            else None,
            source=Source.SIMULATED if simulated else Source.DERIVED,
            evidence_id=deciding.id if deciding else None,
            freshness=freshness(deciding, as_of, stale_ids) if deciding else None,
        )

    test = first(EvidenceKind.AUTOMATED_TEST, automated=True) if control.automatable else None
    outcome = (test.content or {}).get("outcome") if test else None
    if outcome == "fail":  # 1
        return result(
            ImplementationStatus.NOT_IMPLEMENTED,
            AssuranceLevel.L3_TESTED,
            "automated_test_fail",
            test,
        )
    # A verification must come from a person: L4 needs a named assessor.
    verification = first(EvidenceKind.ATTESTATION, decision="verification", automated=False)
    if verification is not None:  # 2
        status = ImplementationStatus((verification.content or {})["status"])
        return result(status, AssuranceLevel.L4_VERIFIED, "verification_decision", verification)
    if outcome == "pass":  # 3
        return result(
            ImplementationStatus.IMPLEMENTED,
            AssuranceLevel.L3_TESTED,
            "automated_test_pass",
            test,
        )
    document = first(EvidenceKind.DOCUMENT_REF)
    if document is not None:  # 4
        return result(
            ImplementationStatus.PARTIALLY_IMPLEMENTED,
            AssuranceLevel.L2_EVIDENCED,
            "document_ref",
            document,
        )
    snapshot = first(EvidenceKind.CONFIG_SNAPSHOT, automated=True) if control.automatable else None
    if snapshot is not None:  # 5
        return result(
            ImplementationStatus.PARTIALLY_IMPLEMENTED,
            AssuranceLevel.L2_EVIDENCED,
            "automated_config_snapshot",
            snapshot,
        )
    attestation = first(EvidenceKind.ATTESTATION, decision="attestation")
    if attestation is not None:
        if (attestation.content or {}).get("status") == ImplementationStatus.NOT_IMPLEMENTED:  # 6
            return result(
                ImplementationStatus.NOT_IMPLEMENTED,
                AssuranceLevel.L1_DECLARED,
                "attestation_not_implemented",
                attestation,
            )
        return result(  # 7
            ImplementationStatus.PARTIALLY_IMPLEMENTED,
            AssuranceLevel.L1_DECLARED,
            "attestation",
            attestation,
        )
    return result(  # 8
        ImplementationStatus.NOT_ASSESSED, AssuranceLevel.L0_INFERRED, "no_evidence", None
    )
