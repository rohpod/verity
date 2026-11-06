"""The stale-graph refusal, the derived rows and the header (ADR 0029, decisions 2, 10 and 11)."""

from datetime import timedelta

import pytest
from export_support import (
    AS_OF,
    LOADED,
    OTHER,
    OWN,
    built_fixture,
    built_from,
    fixture_graph,
    function_config,
    small_graph,
    unassessed_graph,
)
from verity_core.assess.apply import estimate_apply
from verity_core.export import derive
from verity_core.export.build import StaleGraphError, build_snapshot
from verity_core.export.redact import redact
from verity_core.graph.traversals import crosswalk, obligations_for, provider_impact
from verity_core.model.enums import NodeType


def dumped():
    return built_fixture().snapshot.model_dump(mode="json")


def assessed_now():
    """What an assessment of the fixture graph gives at AS_OF, found independently."""
    from itertools import count

    ticks = count()
    return estimate_apply(
        fixture_graph(),
        LOADED.rules,
        LOADED.dates,
        AS_OF,
        lambda: AS_OF + timedelta(seconds=next(ticks) + 1),
        LOADED.tenant,
    )


# --- decision 2: a stale graph is refused ------------------------------------------------


def test_a_graph_that_was_never_assessed_is_refused():
    with pytest.raises(StaleGraphError) as refused:
        build_snapshot(unassessed_graph(), content=LOADED, as_of=AS_OF, data_source="fixture")
    assert "run verity assess first" in str(refused.value)
    assert refused.value.written["assessments"] > 0


def test_a_graph_assessed_long_ago_is_refused_when_the_evidence_has_since_expired():
    with pytest.raises(StaleGraphError):
        build_snapshot(
            fixture_graph(),
            content=LOADED,
            as_of=AS_OF + timedelta(days=120),
            data_source="fixture",
        )


def test_the_refusal_reports_counts_and_no_value():
    with pytest.raises(StaleGraphError) as refused:
        build_snapshot(unassessed_graph(), content=LOADED, as_of=AS_OF, data_source="fixture")
    text = str(refused.value)
    assert "ctl:" not in text and "sys:" not in text and "res:" not in text


def test_an_assessed_graph_at_the_same_as_of_is_accepted_and_the_check_wrote_nothing():
    assert assessed_now().total_written == 0
    assert built_fixture().snapshot.nodes


def test_the_refusal_needs_the_applicability_rules():
    import dataclasses

    with pytest.raises(ValueError, match="applicability"):
        build_snapshot(
            fixture_graph(),
            content=dataclasses.replace(LOADED, rules=None),
            as_of=AS_OF,
            data_source="fixture",
        )


# --- decision 10: findings and statuses are from the one run -----------------------------


def test_findings_statuses_and_results_are_those_of_the_one_assessment():
    result = assessed_now()
    data = dumped()
    assert [(f["code"], f["subject"], f["message"]) for f in data["findings"]] == [
        (f.code, f.subject, f.message) for f in result.findings
    ]
    assert [
        (s["requirement_id"], s["system_id"], s["state"]) for s in data["requirement_statuses"]
    ] == [(s.requirement_id, s.system_id, s.state.value) for s in result.statuses]
    assert [(r["control_id"], r["scope_id"], r["status"]) for r in data["control_results"]] == [
        (r.control_id, r.scope_id, r.status.value) for r in result.results
    ]
    assert {f["code"] for f in data["findings"]} >= {"shadow_ai_candidate", "control_not_met"}


def test_the_seeded_vc060_finding_and_the_shadow_candidate_are_in_the_file():
    findings = dumped()["findings"]
    assert any(f["code"] == "control_not_met" and "VC-060" in f["message"] for f in findings)
    assert any(f["code"] == "shadow_ai_candidate" and f["severity"] == "high" for f in findings)


def test_a_result_resting_on_a_simulated_sign_off_says_so():
    results = dumped()["control_results"]
    assert any(r["simulated"] for r in results) and any(not r["simulated"] for r in results)


# --- decision 10: the traversals are reused, not rewritten -------------------------------


def systems():
    graph = fixture_graph()
    return [n for n in sorted(graph.nodes) if graph.nodes[n]["record"].type is NodeType.AI_SYSTEM]


def test_obligations_are_the_traversals_own_rows_for_every_system():
    graph = fixture_graph()
    data = dumped()["obligations"]
    for system_id in systems():
        expected = obligations_for(graph, system_id)
        got = [r for r in data if r["system_id"] == system_id]
        assert [(r["requirement_id"], r["role"], r["control_id"]) for r in got] == [
            (row.requirement_id, row.role.value, row.control_id) for row in expected
        ]
    assert len(data) == sum(len(obligations_for(graph, s)) for s in systems())


def test_provider_impact_is_the_traversals_own_answer_for_every_provider():
    graph = fixture_graph()
    rows = {r["provider_id"]: r for r in dumped()["provider_impact"]}
    providers = [n for n in graph.nodes if graph.nodes[n]["record"].type is NodeType.PROVIDER]
    assert set(rows) == set(providers) and providers
    for provider_id in providers:
        impact = provider_impact(graph, provider_id)
        assert rows[provider_id]["assessment_ids"] == list(impact.assessment_ids)
        assert [s["system_id"] for s in rows[provider_id]["systems"]] == [
            s.system_id for s in impact.systems
        ]


def test_the_crosswalk_is_the_traversals_own_links_for_every_pair_that_has_any():
    graph = fixture_graph()
    rows = dumped()["crosswalk"]
    assert rows
    for row in rows:
        links = crosswalk(graph, row["requirement_id"], row["to_framework"])
        assert [link["target_requirement_id"] for link in row["links"]] == [
            link.target_requirement_id for link in links
        ]
        assert [link["via_control_id"] for link in row["links"]] == [
            link.via_control_id for link in links
        ]
        assert all(link["strength"] >= 1 for link in row["links"])
        assert row["from_framework"] != row["to_framework"]
    assert len({(r["from_framework"], r["to_framework"]) for r in rows}) >= 2


def test_no_derived_module_computes_a_traversal_itself():
    """`derive.py` calls the traversals and never walks the graph's edges."""
    import ast
    from pathlib import Path

    source = (Path(__file__).parents[2] / "core/verity_core/export/derive.py").read_text()
    names = {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}
    assert not names & {"in_edges", "out_edges", "successors", "predecessors"}
    assert {"obligations_for", "provider_impact", "crosswalk"} <= names
    assert derive.derive


# --- decision 11: provenance and the header ----------------------------------------------

ROWS = (
    "nodes",
    "edges",
    "findings",
    "requirement_statuses",
    "control_results",
    "obligations",
    "provider_impact",
    "crosswalk",
)
SOURCES = {"discovered", "declared", "seeded", "synthetic", "derived", "simulated"}


@pytest.mark.parametrize("name", ROWS)
def test_every_record_and_row_carries_a_provenance_source(name):
    rows = dumped()[name]
    assert rows
    assert {r.get("source") for r in rows} <= SOURCES
    assert all("source" in r for r in rows)


@pytest.mark.parametrize("name", ROWS[2:])
def test_findings_statuses_and_precomputed_rows_are_derived(name):
    assert {r["source"] for r in dumped()[name]} == {"derived"}


def test_the_header_names_the_run_the_source_the_steps_and_what_is_simulated():
    header = dumped()["header"]
    assert header["schema_version"] == 1 and header["data_source"] == "fixture"
    assert header["as_of"] == "2026-11-06T00:00:00Z"
    assert "own account replaced by 000000000000" in header["redaction"]["steps"]
    assert "independent scan before writing" in header["redaction"]["steps"]
    assert header["redaction"]["evidence_rebuilt"] > 0
    simulated = " ".join(header["simulated_components"]).lower()
    assert "mock-bedrock" in simulated or "bedrock" in simulated
    assert "mock-openai" in simulated or "openai" in simulated
    assert "simulated sign-offs" in header["simulated_components"]


def test_the_header_counts_nothing_that_is_a_value():
    text = str(dumped()["header"])
    assert OWN not in text and OTHER not in text


# --- the derived rows go through the same redaction --------------------------------------


def test_derived_rows_follow_the_evidence_id_map_and_the_account_map():
    graph, made = small_graph(function_config(OWN, f"arn:aws:iam::{OTHER}:root"))
    ((_, original),) = made
    extras = {
        "findings": [
            {"source": "derived", "message": f"see {original.id} and arn:aws:iam::{OTHER}:root"}
        ]
    }
    redacted = redact(graph, extras)
    (row,) = redacted.extras["findings"]
    new_id = redacted.evidence_ids[original.id]
    assert new_id in row["message"] and original.id not in row["message"]
    assert OTHER not in row["message"] and "acct_1" in row["message"]


def test_a_derived_row_cannot_keep_an_old_evidence_id():
    graph, made = small_graph(function_config(OWN))
    snapshot = built_from(graph).snapshot.model_dump(mode="json")
    ((_, original),) = made
    assert original.id not in str(snapshot)


def test_every_evidence_id_in_a_derived_row_is_a_node_in_the_file():
    data = dumped()
    node_ids = {n["id"] for n in data["nodes"]}
    named = {r["evidence_id"] for r in data["control_results"] if r["evidence_id"]}
    named |= {e for r in data["obligations"] for e in r["evidence_ids"]}
    assert named and named <= node_ids
