"""Reads `decisions/*.yaml`: the human decisions that governance as code keeps in git.

Each decision (a risk tier, an attestation, a verification, a document or a revocation)
becomes an Evidence node with inline content, plus an `ABOUT` edge to the node it
concerns (ADR 0019). `Evidence.content_ref` has to sit under `evidence/`, so the decision file
is recorded by path and sha256 inside the content instead. The commit SHA is not recorded here:
it would change the hash on every commit, so it is looked up at export (D10).
"""

import hashlib
from datetime import UTC, date, datetime, time
from pathlib import Path

from verity_core.content.schema import (
    DecisionFile,
    DecisionIn,
    DocumentDecision,
    RevocationDecision,
    RiskTierDecision,
)
from verity_core.content.yamlio import ContentError, parse, reading
from verity_core.model import ids
from verity_core.model.edges import Edge, PlainEdge
from verity_core.model.enums import EdgeType, EvidenceKind, NodeType, Source
from verity_core.model.evidence import Evidence


def load_decisions(root: Path, tenant: str) -> tuple[list[Evidence], list[Edge]]:
    """`root` is the content directory. Paths in a decision are relative to its parent, the
    repository root, because `evidence/` sits beside `content/`."""
    repo_root = root.parent
    evidence: list[Evidence] = []
    edges: list[Edge] = []
    seen: dict[str, Path] = {}

    for path in sorted((root / "decisions").glob("*.yaml")):
        decision = parse(path, DecisionFile).root
        with reading(path):
            if decision.id in seen:
                raise ContentError(path, f"decision {decision.id!r} is also in {seen[decision.id]}")
            seen[decision.id] = path
            record = _evidence(decision, path, repo_root, tenant)
            evidence.append(record)
            edges.append(
                PlainEdge(
                    src=record.id,
                    dst=record.subject,
                    type=EdgeType.ABOUT,
                    tenant=tenant,
                    source=record.source,
                )
            )
    return evidence, edges


def _evidence(decision: DecisionIn, path: Path, repo_root: Path, tenant: str) -> Evidence:
    file_bytes = path.read_bytes()
    content = {
        "decision_id": decision.id,
        "decision_kind": decision.kind,
        "decision_file": path.relative_to(repo_root).as_posix(),
        "file_sha256": hashlib.sha256(file_bytes).hexdigest(),
        "statement": decision.statement,
    }
    if isinstance(decision, RiskTierDecision):
        subject = ids.check_id(decision.system, NodeType.AI_SYSTEM)
        content |= {"system": subject, "tier": decision.tier, "basis": decision.basis}
        if decision.condition is not None:
            content |= {"condition": decision.condition, "profiling": decision.profiling}
        kind = EvidenceKind.ATTESTATION
    elif isinstance(decision, RevocationDecision):
        subject = _scope_id(decision.subject)
        content["subject"] = subject
        kind = EvidenceKind.ATTESTATION
    else:
        subject = _scope_id(decision.scope)
        content |= {"control": ids.control_id(decision.control), "scope": subject}
        if isinstance(decision, DocumentDecision):
            Evidence._check_content_ref(decision.path)  # noqa: SLF001
            if not (repo_root / decision.path).is_file():
                raise ContentError(path, f"document {decision.path!r} does not exist")
            content["path"] = decision.path
            kind = EvidenceKind.DOCUMENT_REF
        else:
            content["status"] = decision.status
            kind = EvidenceKind.ATTESTATION
    if decision.supersedes:  # left out when empty, so a decision's hash does not change (ADR 0020)
        content["supersedes"] = list(decision.supersedes)
    return Evidence.build(
        subject=subject,
        collector=decision.by,
        collected_at=_start_of(decision.decided_on),
        content=content,
        kind=kind,
        valid_until=_end_of(decision.valid_until),
        tenant=tenant,
        source=Source.SIMULATED if decision.simulated else Source.DECLARED,
    )


def _scope_id(value: str) -> str:
    """An organisation, system or provider: the scopes a ControlAssessment may have."""
    node_type = ids.node_type_of(value)
    if node_type not in {NodeType.ORGANISATION, NodeType.AI_SYSTEM, NodeType.PROVIDER}:
        raise ValueError(f"{value!r} is not an organisation, system or provider")
    return value


def _start_of(day: date) -> datetime:
    return datetime.combine(day, time.min, UTC)


def _end_of(day: date) -> datetime:
    """A decision is valid through the whole of its `valid_until` day."""
    return datetime.combine(day, time.max, UTC)
