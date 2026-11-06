from datetime import UTC, datetime

import pytest
from discovery_support import CONTENT_LOADED, crawl_fixture, seeded
from factories import COMMON
from verity_core.assess.apply import apply_assessment
from verity_core.assess.findings import derive_findings
from verity_core.graph.loader import build_graph
from verity_core.graph.memory import InMemoryRepository
from verity_core.model import ids
from verity_core.model.edges import PlainEdge
from verity_core.model.enums import AiLikelihood as L
from verity_core.model.enums import EdgeType, SystemKind
from verity_core.model.nodes import AISystem, Candidate
from verity_core.rules.finding import Severity

AS_OF = datetime(2026, 11, 6, tzinfo=UTC)


def candidate(name, likelihood) -> Candidate:
    return Candidate(
        id=ids.candidate_id(name),
        name=name,
        ai_likelihood=likelihood,
        signals=["env_ai_name"],
        **COMMON,
    )


def shadow(graph):
    return [f for f in derive_findings(graph, AS_OF, [], []) if f.code == "shadow_ai_candidate"]


@pytest.mark.parametrize(
    ("likelihood", "severity"),
    [
        (L.DECLARED, Severity.HIGH),
        (L.CONFIRMED_USAGE, Severity.HIGH),
        (L.PROBABLE, Severity.HIGH),
        (L.POSSIBLE, Severity.MEDIUM),
    ],
)
def test_severity_follows_how_strongly_the_signals_point_to_ai(likelihood, severity):
    found = shadow(build_graph([candidate("x", likelihood)], []))
    assert [(f.severity, f.subject) for f in found] == [(severity, "cand:x")]
    assert "env_ai_name" in found[0].message


def test_a_promoted_candidate_raises_nothing():
    system = AISystem(
        id=ids.system_id("s"), name="S", purpose="p", kind=SystemKind.GENERATIVE_AI, **COMMON
    )
    edge = PlainEdge(src="cand:x", dst=system.id, type=EdgeType.PROMOTED_TO, **COMMON)
    graph = build_graph([candidate("x", L.PROBABLE), system], [edge])
    assert shadow(graph) == []


def test_each_open_candidate_gets_one_finding():
    graph = build_graph([candidate("a", L.PROBABLE), candidate("b", L.POSSIBLE)], [])
    assert [f.subject for f in shadow(graph)] == ["cand:a", "cand:b"]


def test_the_real_content_without_a_crawl_still_has_27_high_findings(clock):
    repo = InMemoryRepository("kestrel", clock)
    seeded(repo, clock, CONTENT_LOADED)
    result = apply_assessment(repo, CONTENT_LOADED.rules, CONTENT_LOADED.dates, clock.now, clock)
    assert sum(f.severity is Severity.HIGH for f in result.findings) == 27
    assert not [f for f in result.findings if f.code == "shadow_ai_candidate"]


def test_the_crawl_adds_the_shadow_finding_and_the_vc060_finding(clock):
    repo = InMemoryRepository("kestrel", clock)
    seeded(repo, clock, CONTENT_LOADED)
    crawl_fixture(repo, clock, content=CONTENT_LOADED)
    clock.advance(minutes=5)
    result = apply_assessment(repo, CONTENT_LOADED.rules, CONTENT_LOADED.dates, clock.now, clock)
    high = {(f.code, f.subject) for f in result.findings if f.severity is Severity.HIGH}
    assert ("shadow_ai_candidate", "cand:shadow-summariser") in high
    assert ("control_not_met", "sys:support-assistant") in high
    assert sum(f.severity is Severity.HIGH for f in result.findings) == 29
