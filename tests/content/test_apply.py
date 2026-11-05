import copy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from content_samples import good_files, good_org, write_tree
from verity_core.assess.apply import apply_assessment, estimate_apply
from verity_core.content.loader import load_content
from verity_core.content.seed import seed
from verity_core.graph.integrity import check_integrity
from verity_core.graph.memory import InMemoryRepository
from verity_core.model import ids
from verity_core.model.enums import Direction, EdgeType, NodeType

REAL = Path(__file__).parents[2] / "content"
AS_OF = datetime(2026, 11, 5, tzinfo=UTC)


@pytest.fixture(scope="module")
def content():
    return load_content(REAL)


@pytest.fixture
def seeded(clock, content):
    """The real content on the in-memory repository. The real content is too big for moto to
    seed in a test (minutes), so the real table's backend is covered by `small_tree` below."""
    repo = InMemoryRepository("kestrel", clock)
    seed(repo, content, clock)
    clock.now += timedelta(minutes=5)
    return repo


def run(repo, clock, content, **kw):
    return apply_assessment(repo, content.rules, content.dates, AS_OF, clock, **kw)


def test_a_first_run_writes_edges_and_assessments_and_leaves_a_sound_graph(seeded, clock, content):
    result = run(seeded, clock, content)
    assert result.written["applies_to"] > 0
    assert result.written["assessments"] == len(result.results) > 0
    assert check_integrity(seeded.load_graph()) == []


def test_a_second_run_writes_nothing(seeded, clock, content):
    run(seeded, clock, content)
    clock.now += timedelta(minutes=5)
    again = run(seeded, clock, content)
    assert again.total_written == 0
    assert again.unchanged_assessments == len(again.results)


def test_assessed_at_is_kept_while_status_and_level_are_unchanged(seeded, clock, content):
    run(seeded, clock, content)
    node_id = ids.ca_id("ctl:VC-032", "sys:talent-screening")
    first = seeded.get_node(node_id).assessed_at
    clock.now += timedelta(days=3)
    apply_assessment(seeded, content.rules, content.dates, AS_OF + timedelta(days=3), clock)
    assert seeded.get_node(node_id).assessed_at == first


def test_a_verification_gets_all_four_assessment_edges(seeded, clock, content):
    run(seeded, clock, content)
    node_id = ids.ca_id("ctl:VC-032", "sys:talent-screening")
    edges = {e.type for e in seeded.neighbors(node_id, Direction.OUT)} | {
        e.type for e in seeded.neighbors(node_id, Direction.IN)
    }
    assert {
        EdgeType.ASSESSES,
        EdgeType.SCOPED_TO,
        EdgeType.SUPPORTS,
        EdgeType.ASSESSED,
    } <= edges


def test_a_derived_edge_that_is_no_longer_produced_is_closed(seeded, clock, content):
    run(seeded, clock, content)
    before = len(seeded.neighbors("sys:talent-screening", Direction.IN, EdgeType.APPLIES_TO))
    assert before > 0
    # Rejecting the high-risk tier would remove the Chapter III edges; simulate with no rules.
    empty = content.rules.model_copy(update={"rules": []})
    clock.now += timedelta(minutes=5)
    result = apply_assessment(seeded, empty, content.dates, AS_OF, clock)
    assert result.written["applies_to_closed"] > 0
    assert not seeded.neighbors("sys:talent-screening", Direction.IN, EdgeType.APPLIES_TO)


def test_a_newer_deciding_evidence_closes_the_old_supports_edge(seeded, clock, content):
    run(seeded, clock, content)
    node_id = ids.ca_id("ctl:VC-032", "sys:talent-screening")
    supports = seeded.neighbors(node_id, Direction.IN, EdgeType.SUPPORTS)
    assert len(supports) == 1
    # After the decision expires, nothing supports it: the edge must close.
    clock.now += timedelta(minutes=5)
    late = datetime(2028, 1, 1, tzinfo=UTC)
    result = apply_assessment(seeded, content.rules, content.dates, late, clock)
    assert result.written["assessment_edges_closed"] > 0
    assert not seeded.neighbors(node_id, Direction.IN, EdgeType.SUPPORTS)


def test_system_limits_what_is_assessed_and_written(seeded, clock, content):
    result = run(seeded, clock, content, system_id="sys:talent-screening")
    assert {s.system_id for s in result.statuses} == {"sys:talent-screening"}
    assert seeded.neighbors("sys:talent-screening", Direction.IN, EdgeType.APPLIES_TO)
    assert not seeded.neighbors("sys:support-assistant", Direction.IN, EdgeType.APPLIES_TO)
    assert len(result.results) < len(run(seeded, clock, content).results)


def test_an_unknown_system_is_refused(seeded, clock, content):
    with pytest.raises(ValueError, match="not a system"):
        run(seeded, clock, content, system_id="sys:nowhere")


def test_the_estimate_matches_the_first_real_run(seeded, clock, content):
    graph = seeded.load_graph()
    planned = estimate_apply(graph, content.rules, content.dates, AS_OF, clock, "kestrel")
    clock.now += timedelta(minutes=5)
    actual = run(seeded, clock, content)
    assert planned.written == actual.written
    assert len(seeded.nodes_by_type(NodeType.CONTROL_ASSESSMENT)) == len(actual.results)


# --- both repositories, on a small tree -----------------------------------------------------


def small_tree(tmp_path):
    files = copy.deepcopy(good_files())
    files["org/kestrel.yaml"] = good_org()
    files["rules/applicability.yaml"] = {
        "annex_iii_domains": {"employment": "Annex III, point 4"},
        "rules": [
            {
                "id": "lit",
                "requirements": ["req:euaia:art4"],
                "target": "organisation",
                "role": "held",
                "date": "euaia-example",
            },
            {
                "id": "disclosure",
                "requirements": ["req:euaia:art50-1"],
                "target": "system",
                "role": "provider",
                "reads": ["interacts_with_people"],
            },
        ],
    }
    files["decisions/v.yaml"] = {
        "id": "v",
        "kind": "verification",
        "decided_on": "2026-11-01",
        "by": "person:l-ivanova",
        "valid_until": "2027-11-01",
        "simulated": True,
        "statement": "Simulated sign-off by a fictional person.",
        "control": "VC-012",
        "scope": "sys:faq-bot",
        "status": "implemented",
    }
    files["decisions/a.yaml"] = {
        **files["decisions/v.yaml"],
        "id": "a",
        "kind": "attestation",
        "control": "VC-001",
        "scope": "org:kestrel",
    }
    return load_content(write_tree(tmp_path / "content", files))


def test_a_second_run_writes_nothing_on_both_repositories(repo, clock, tmp_path):
    small = small_tree(tmp_path)
    seed(repo, small, clock)
    clock.now += timedelta(minutes=5)
    first = apply_assessment(repo, small.rules, small.dates, AS_OF, clock)
    assert first.written["applies_to"] > 0
    assert first.written["assessments"] > 0
    assert first.written["assessment_edges"] > 0
    clock.now += timedelta(minutes=5)
    second = apply_assessment(repo, small.rules, small.dates, AS_OF, clock)
    assert second.total_written == 0
    assert second.unchanged_assessments == len(second.results)
    assert check_integrity(repo.load_graph()) == []
