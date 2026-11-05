"""Build small graphs for the applicability tests. The requirements, rules and dates are the
real ones under `content/`; the organisation, systems and decisions are invented here."""

from datetime import UTC, date, datetime
from pathlib import Path

from verity_core.content.loader import load_content
from verity_core.graph.loader import build_graph
from verity_core.model import ids
from verity_core.model.edges import PlainEdge
from verity_core.model.enums import EdgeType, EvidenceKind, Role, Source, SystemKind
from verity_core.model.evidence import Evidence
from verity_core.model.nodes import AISystem, Organisation
from verity_core.rules.applicability import applicable_edges

REAL = Path(__file__).parents[2] / "content"
CONTENT = load_content(REAL)
TENANT = "kestrel"
ORG = "org:kestrel"
COMMON = {"tenant": TENANT, "source": Source.SYNTHETIC}
AS_OF = datetime(2026, 11, 10, tzinfo=UTC)

PROVIDER_REQS = [
    "art9",
    "art9-2a",
    "art10",
    "art10-2ah",
    "art10-2fg",
    "art11",
    "art12",
    "art13",
    "art14",
    "art25-4",
]
DEPLOYER_REQS = ["art26", "art26-2", "art26-7"]


def date_of(date_id: str) -> date:
    return next(d.date for d in CONTENT.dates if d.id == date_id)


def system(slug: str, **facts) -> AISystem:
    return AISystem(
        id=ids.system_id(slug),
        name=slug,
        purpose="Invented for the tests",
        kind=SystemKind.CLASSICAL_ML,
        **COMMON,
        **facts,
    )


def decision(
    system_id: str, tier: str, decided_on: date, name: str = "d", supersedes=()
) -> Evidence:
    """A `risk_tier` decision as `content/decisions.py` builds it."""
    extra = {"supersedes": list(supersedes)} if supersedes else {}
    return Evidence.build(
        subject=system_id,
        collector="person:l-ivanova",
        collected_at=datetime(decided_on.year, decided_on.month, decided_on.day, tzinfo=UTC),
        valid_until=datetime(2030, 1, 1, tzinfo=UTC),
        kind=EvidenceKind.ATTESTATION,
        content={"decision_id": name, "decision_kind": "risk_tier", "tier": tier, **extra},
        **COMMON,
    )


def revocation(system_id: str, decided_on: date, supersedes, name: str = "r") -> Evidence:
    """A `revocation` decision as `content/decisions.py` builds it."""
    return Evidence.build(
        subject=system_id,
        collector="person:l-ivanova",
        collected_at=datetime(decided_on.year, decided_on.month, decided_on.day, tzinfo=UTC),
        valid_until=datetime(2030, 1, 1, tzinfo=UTC),
        kind=EvidenceKind.ATTESTATION,
        content={
            "decision_id": name,
            "decision_kind": "revocation",
            "subject": system_id,
            "supersedes": list(supersedes),
        },
        **COMMON,
    )


def run(
    *systems: AISystem,
    decisions: tuple[Evidence, ...] = (),
    organisation=True,
    as_of: datetime = AS_OF,
):
    nodes = [*CONTENT.frameworks, *CONTENT.requirements, *systems, *decisions]
    if organisation:
        nodes.append(Organisation(id=ORG, name="Kestrel Cloud Ltd", **COMMON))
    edges = [e for e in CONTENT.edges if e.type is EdgeType.PART_OF]
    edges += [PlainEdge(src=d.id, dst=d.subject, type=EdgeType.ABOUT, **COMMON) for d in decisions]
    graph = build_graph(nodes, edges)
    return applicable_edges(graph, CONTENT.rules, CONTENT.dates, as_of)


def edges_to(edges, target: str) -> dict[tuple[str, Role], object]:
    """The edges to `target`, keyed by (requirement slug, role)."""
    return {(e.src.split(":")[-1], e.role): e for e in edges if e.dst == target}


def codes(findings, subject=None) -> list[str]:
    return [f.code for f in findings if subject in (None, f.subject)]
