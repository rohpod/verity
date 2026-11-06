"""The Candidate lifecycle (ADR 0021, decision 12)."""

from discovery_support import (
    MINI,
    crawl_fixture,
    edited_fixture,
    of_type,
    open_edges,
    seeded,
)
from verity_core.discovery.names import function_id
from verity_core.model.enums import AiLikelihood as L
from verity_core.model.enums import EdgeType, NodeType

SHADOW = "cand:shadow-summariser"


def tag(function, system):
    def edit(raw):
        arn = next(f["FunctionArn"] for f in raw["functions"] if f["FunctionName"] == function)
        raw["tag_mappings"].append(
            {"ResourceARN": arn, "Tags": [{"Key": "ai:system-id", "Value": system}]}
        )

    return edit


def untag_all(raw):
    raw["tag_mappings"] = [m for m in raw["tag_mappings"] if "shadow" not in m["ResourceARN"]]


def candidates(repo):
    return {c.id: c for c in of_type(repo, NodeType.CANDIDATE)}


def test_an_unregistered_function_that_looks_like_ai_is_created_once(repo, clock):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(hours=1)
    again = crawl_fixture(repo, clock)
    assert set(candidates(repo)) == {SHADOW}
    assert len(repo.history(SHADOW)) == 1
    assert again.written.get("candidates", 0) == 0


def test_adding_a_tag_promotes_it_and_it_stays_open(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(hours=1)
    crawl_fixture(
        repo, clock, edited_fixture(tmp_path, tag("shadow-summariser", "sys:lead-scoring"))
    )
    assert repo.get_node(SHADOW).valid_to is None
    assert open_edges(repo, EdgeType.PROMOTED_TO) == {(SHADOW, "sys:lead-scoring")}
    assert ("sys:lead-scoring", function_id("shadow-summariser")) in open_edges(
        repo, EdgeType.RUNS_ON
    )


def test_removing_the_tag_makes_it_a_shadow_candidate_again(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(hours=1)
    promoted = edited_fixture(tmp_path, tag("shadow-summariser", "sys:lead-scoring"))
    crawl_fixture(repo, clock, promoted)
    clock.advance(hours=1)
    crawl_fixture(repo, clock)  # the original estate: no tag
    assert repo.get_node(SHADOW).valid_to is None
    assert open_edges(repo, EdgeType.PROMOTED_TO) == set()
    assert ("sys:lead-scoring", function_id("shadow-summariser")) not in open_edges(
        repo, EdgeType.RUNS_ON
    )


def test_it_ends_when_the_signal_goes_and_reopens_when_it_returns(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    # No name rule, and no AI env var: nothing left that scores.
    quieter = MINI.signals.model_copy(
        update={"signals": [s for s in MINI.signals.signals if s.id != "name_ai_token"]}
    )
    content = type(MINI)(**{**MINI.__dict__, "signals": quieter})

    def calm(raw):
        found = next(f for f in raw["functions"] if f["FunctionName"] == "shadow-summariser")
        found["Environment"]["Variables"] = {"LOG_LEVEL": "x"}

    clock.advance(hours=1)
    ended = crawl_fixture(repo, clock, edited_fixture(tmp_path, calm), content)
    assert repo.get_node(SHADOW).valid_to == clock.now
    assert ended.written["candidates_ended"] == 1 and ended.candidates == ()
    assert SHADOW not in {c.id for c in of_type(repo, NodeType.CANDIDATE) if c.valid_to is None}

    clock.advance(hours=1)
    crawl_fixture(repo, clock)
    assert repo.get_node(SHADOW).valid_to is None
    assert (SHADOW, function_id("shadow-summariser")) in open_edges(repo, EdgeType.DERIVED_FROM)


def test_a_likelihood_that_changes_updates_the_open_candidate(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(hours=1)

    def calm(raw):
        found = next(f for f in raw["functions"] if f["FunctionName"] == "shadow-summariser")
        found["Environment"]["Variables"] = {"LOG_LEVEL": "x"}

    crawl_fixture(repo, clock, edited_fixture(tmp_path, calm))
    candidate = repo.get_node(SHADOW)
    assert (candidate.ai_likelihood, candidate.signals) == (L.POSSIBLE, ["name_ai_token"])
    assert len(repo.history(SHADOW)) == 2


def test_naming_a_system_that_does_not_exist_makes_a_declared_candidate(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock, edited_fixture(tmp_path, tag("invoice-renderer", "sys:ghost")))
    candidate = candidates(repo)["cand:invoice-renderer"]
    assert candidate.ai_likelihood is L.DECLARED
    assert candidate.signals == ["names_unknown_system", "tag_system_id"]
    assert open_edges(repo, EdgeType.PROMOTED_TO) == set()


def test_a_platform_component_never_becomes_a_candidate(repo, clock):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    assert "cand:mock-openai" not in candidates(repo)
