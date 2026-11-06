"""End to end: the recorded estate through `crawl`, on both repository backends."""

from collections import Counter

from discovery_support import (
    CANARY,
    crawl_fixture,
    dump,
    edited_fixture,
    of_type,
    open_edges,
    role_of,
    seeded,
    table_text,
)
from verity_core.discovery.names import function_id, role_id, table_id
from verity_core.discovery.persist import ForbiddenWriteError, Plan, persist
from verity_core.graph.traversals import stale_by_change
from verity_core.model import ids
from verity_core.model.edges import PlainEdge
from verity_core.model.enums import AiLikelihood as L
from verity_core.model.enums import EdgeType, EvidenceKind, NodeType, Source
from verity_core.model.nodes import DiscoveryRun

SIGNALS = {
    "support-assistant": (
        L.DECLARED,
        ("env_ai_name", "iam_ai_action", "name_ai_token", "tag_system_id"),
    ),
    "talent-screening": (L.DECLARED, ("manifest",)),
    "contract-insights": (L.DECLARED, ("env_ai_name", "manifest", "tag_system_id")),
    "shadow-summariser": (L.PROBABLE, ("env_ai_name", "name_ai_token")),
    "invoice-renderer": (L.NONE, ()),
    "mock-openai": (L.NONE, ("platform_component",)),
}


def resources(repo):
    return {r.name: r for r in of_type(repo, NodeType.AWS_RESOURCE) if r.resource_type == "lambda"}


def test_the_estate_is_scored_as_the_plan_says(repo, clock):
    seeded(repo, clock)
    report = crawl_fixture(repo, clock)
    assert {name: (level, signals) for name, level, signals in report.functions} == SIGNALS
    for name, resource in resources(repo).items():
        assert (resource.ai_likelihood, tuple(resource.signals)) == SIGNALS[name]


def test_only_shadow_summariser_becomes_a_candidate(repo, clock):
    seeded(repo, clock)
    report = crawl_fixture(repo, clock)
    (candidate,) = of_type(repo, NodeType.CANDIDATE)
    assert candidate.id == "cand:shadow-summariser"
    assert (candidate.ai_likelihood, candidate.signals) == (
        L.PROBABLE,
        ["env_ai_name", "name_ai_token"],
    )
    assert report.candidates == (
        ("shadow-summariser", L.PROBABLE, ("env_ai_name", "name_ai_token")),
    )
    assert open_edges(repo, EdgeType.DERIVED_FROM) == {
        ("cand:shadow-summariser", function_id("shadow-summariser"))
    }
    assert not any(c.id == "cand:invoice-renderer" for c in of_type(repo, NodeType.CANDIDATE))


def test_roles_and_tables_stay_unscored(repo, clock):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    others = [r for r in of_type(repo, NodeType.AWS_RESOURCE) if r.resource_type != "lambda"]
    assert len(others) == 7
    assert all(r.ai_likelihood is None and r.signals == [] for r in others)


def test_functions_run_on_assume_and_call(repo, clock):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    assert open_edges(repo, EdgeType.RUNS_ON) == {
        (f"sys:{name}", function_id(name))
        for name in ("support-assistant", "talent-screening", "contract-insights")
    }
    assert len(open_edges(repo, EdgeType.ASSUMES)) == 6
    assert (function_id("support-assistant"), role_id("support-assistant-role")) in open_edges(
        repo, EdgeType.ASSUMES
    )
    assert open_edges(repo, EdgeType.CALLS) == {
        (function_id("support-assistant"), table_id("verity-graph"))
    }


def test_evidence_is_written_for_every_resource_and_each_system_with_a_role(repo, clock):
    seeded(repo, clock)
    report = crawl_fixture(repo, clock)
    items = of_type(repo, NodeType.EVIDENCE)
    snapshots = [e for e in items if e.kind is EvidenceKind.CONFIG_SNAPSHOT]
    checks = [e for e in items if e.kind is EvidenceKind.AUTOMATED_TEST]
    assert (len(snapshots), len(checks)) == (13, 3)
    assert report.summary["evidence_written"] == 16
    assert {e.subject for e in checks} == {
        "sys:support-assistant",
        "sys:talent-screening",
        "sys:contract-insights",
    }


def test_the_run_is_recorded_with_its_counts(repo, clock):
    seeded(repo, clock)
    started = clock.now
    report = crawl_fixture(repo, clock)
    (run,) = of_type(repo, NodeType.DISCOVERY_RUN)
    assert run.id == ids.discovery_run_id(started) == report.run_id
    assert run.started_at == started and run.finished_at is not None
    assert run.summary["functions"] == 6 and run.summary["resources_new"] == 13
    assert run.summary["largest_evidence_bytes"] > 0
    assert open_edges(repo, EdgeType.OBSERVED) == {
        (run.id, r.id) for r in of_type(repo, NodeType.AWS_RESOURCE)
    }


def test_a_second_crawl_writes_one_run_and_nothing_else(repo, clock):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(hours=1)
    again = crawl_fixture(repo, clock)
    assert again.written == Counter(runs=1)
    runs = of_type(repo, NodeType.DISCOVERY_RUN)
    assert len(runs) == 2
    assert [len(repo.history(r.id)) for r in runs] == [2, 2]
    assert all(len(repo.history(r.id)) == 1 for r in of_type(repo, NodeType.AWS_RESOURCE))
    assert of_type(repo, NodeType.CHANGE_EVENT) == []
    assert len(of_type(repo, NodeType.EVIDENCE)) == 16


def test_evidence_is_refreshed_when_8_days_or_less_remain(repo, clock):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(days=21)  # 9 days left
    assert crawl_fixture(repo, clock).written == Counter(runs=1)
    clock.advance(days=1)  # the first batch has 8 days left
    refreshed = crawl_fixture(repo, clock)
    assert set(refreshed.written) == {"runs", "evidence", "evidence_edges"}
    assert refreshed.written["evidence"] == 16


def test_a_jump_of_23_days_adds_only_refreshed_evidence(repo, clock):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(days=23)
    refreshed = crawl_fixture(repo, clock)
    assert set(refreshed.written) == {"runs", "evidence", "evidence_edges"}
    assert len(of_type(repo, NodeType.EVIDENCE)) == 32
    assert all(len(repo.history(r.id)) == 1 for r in of_type(repo, NodeType.AWS_RESOURCE))


def test_a_changed_role_gives_a_change_event_and_makes_its_evidence_stale(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    before = {e.id for e in of_type(repo, NodeType.EVIDENCE)}
    clock.advance(hours=1)

    def widen(raw):
        statement = {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": "*"}
        role_of(raw, "support-assistant")["inline_policies"].append(
            {
                "PolicyName": "extra",
                "PolicyDocument": {"Version": "2012-10-17", "Statement": [statement]},
            }
        )

    report = crawl_fixture(repo, clock, edited_fixture(tmp_path, widen))
    role = role_id("support-assistant-role")
    assert report.changes == (role,)
    (change,) = of_type(repo, NodeType.CHANGE_EVENT)
    assert change.detected_at == clock.now
    assert change.previous_config_hash != change.new_config_hash
    assert change.id == ids.change_event_id(report.run_id, role)
    assert report.written["changes"] == report.written["change_edges"] == 1
    assert report.written["resources"] == 1 and report.written["observed"] == 1

    graph = repo.load_graph()
    stale = {item.evidence_id for item in stale_by_change(graph, change.id).evidence}
    old_snapshot = next(
        e.id for e in of_type(repo, NodeType.EVIDENCE) if e.id in before and e.subject == role
    )
    old_check = next(
        e.id
        for e in of_type(repo, NodeType.EVIDENCE)
        if e.id in before and e.subject == "sys:support-assistant"
    )
    assert stale == {old_snapshot, old_check}
    new = [e for e in of_type(repo, NodeType.EVIDENCE) if e.id not in before]
    assert {e.subject for e in new} == {role, "sys:support-assistant"}
    assert all(e.collected_at >= change.detected_at for e in new)
    assert not {e.id for e in new} & stale


def test_a_new_env_var_name_is_a_change_but_a_new_value_is_not(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(hours=1)

    def new_value(raw):
        for f in raw["functions"]:
            for name in f.get("Environment", {}).get("Variables", {}):
                f["Environment"]["Variables"][name] = "a different value"

    quiet = crawl_fixture(repo, clock, edited_fixture(tmp_path, new_value))
    assert quiet.written == Counter(runs=1)

    clock.advance(hours=1)

    def new_name(raw):
        found = next(f for f in raw["functions"] if f["FunctionName"] == "invoice-renderer")
        found["Environment"]["Variables"]["EXTRA_SETTING"] = "x"

    loud = crawl_fixture(repo, clock, edited_fixture(tmp_path, new_name))
    assert loud.changes == (function_id("invoice-renderer"),)
    assert resources(repo)["invoice-renderer"].env_var_names == ["EXTRA_SETTING", "TEMPLATE_BUCKET"]


def test_a_changed_description_is_not_a_change(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(hours=1)

    def reword(raw):
        raw["functions"][4]["Description"] = "Renders invoices, now faster"

    assert crawl_fixture(repo, clock, edited_fixture(tmp_path, reword)).written == Counter(runs=1)


def test_the_canary_is_nowhere_after_a_crawl(repo, clock, capsys, caplog):
    seeded(repo, clock)
    report = crawl_fixture(repo, clock)
    clock.advance(hours=1)
    again = crawl_fixture(repo, clock)
    out = capsys.readouterr()
    everything = "\n".join(
        [dump(repo), table_text(repo), out.out, out.err, caplog.text, repr(report), repr(again)]
    )
    assert CANARY not in everything
    assert "000000000000" not in everything
    assert "<account>" in everything  # ARNs in evidence are kept, cleaned


def test_the_crawler_never_touches_the_seeded_systems(repo, clock):
    seeded(repo, clock)
    before = {
        s.id: (s.model_dump(), len(repo.history(s.id))) for s in of_type(repo, NodeType.AI_SYSTEM)
    }
    crawl_fixture(repo, clock)
    clock.advance(hours=1)
    crawl_fixture(repo, clock)
    after = {
        s.id: (s.model_dump(), len(repo.history(s.id))) for s in of_type(repo, NodeType.AI_SYSTEM)
    }
    assert before == after
    assert {"sys:support-assistant", "sys:talent-screening"} <= set(after)


def test_persist_refuses_a_type_the_crawler_does_not_own(repo, clock):
    seeded(repo, clock)
    system = of_type(repo, NodeType.AI_SYSTEM)[0]
    run = DiscoveryRun(
        id=ids.discovery_run_id(clock.now),
        mode="full",
        started_at=clock.now,
        crawler_version="x",
        tenant=system.tenant,
        source=Source.SIMULATED,
    )
    plan = Plan(run=run, started=clock.now, summary={})
    plan.candidates = [system]  # an AISystem where only a Candidate may go
    try:
        persist(repo, plan, clock)
    except ForbiddenWriteError as exc:
        assert "AISystem" in str(exc)
    else:
        raise AssertionError("expected a refusal")
    assert of_type(repo, NodeType.DISCOVERY_RUN) == []

    edge = PlainEdge(
        src=system.id,
        dst=ids.model_id("bedrock-fm"),
        type=EdgeType.USES_MODEL,
        tenant=system.tenant,
        source=Source.SIMULATED,
    )
    clean = Plan(run=run, started=clock.now, summary={}, relations=[edge])
    try:
        persist(repo, clean, clock)
    except ForbiddenWriteError as exc:
        assert "USES_MODEL" in str(exc)
    else:
        raise AssertionError("expected a refusal")
    assert of_type(repo, NodeType.DISCOVERY_RUN) == []


def test_evidence_over_the_cap_is_summarised_and_never_refused(repo, clock, tmp_path):
    seeded(repo, clock)

    def huge(raw):
        actions = [f"s3:ExampleAction{i:04d}WithALongishName" for i in range(900)]
        statement = {"Effect": "Allow", "Action": actions + ["bedrock:Converse"], "Resource": "*"}
        role_of(raw, "invoice-renderer")["inline_policies"].append(
            {
                "PolicyName": "big",
                "PolicyDocument": {"Version": "2012-10-17", "Statement": [statement]},
            }
        )

    report = crawl_fixture(repo, clock, edited_fixture(tmp_path, huge))
    assert report.summary["largest_evidence_bytes"] > 30_000
    role = role_id("invoice-renderer-role")
    (snapshot,) = [e for e in of_type(repo, NodeType.EVIDENCE) if e.subject == role]
    stored = repo.get_node(role)
    assert snapshot.content == {
        "truncated": True,
        "config_hash": stored.config_hash,
        "ai_actions": ["bedrock:Converse"],
        "statement_count": 2,
    }


def test_a_function_that_disappears_is_ended_and_reopens_when_it_returns(repo, clock, tmp_path):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    clock.advance(hours=1)

    def drop(raw):
        raw["functions"] = [f for f in raw["functions"] if f["FunctionName"] != "shadow-summariser"]

    gone = crawl_fixture(repo, clock, edited_fixture(tmp_path, drop))
    resource = repo.get_node(function_id("shadow-summariser"))
    assert resource.valid_to == clock.now
    assert gone.written["resources_ended"] == 1 and gone.written["candidates_ended"] == 1
    assert gone.changes == ()
    assert of_type(repo, NodeType.CHANGE_EVENT) == []
    assert repo.get_node("cand:shadow-summariser").valid_to == clock.now
    graph = repo.load_graph()
    assert function_id("shadow-summariser") not in graph
    assert not any(function_id("shadow-summariser") in (u, v) for u, v in graph.edges())

    clock.advance(hours=1)
    back = crawl_fixture(repo, clock)
    assert repo.get_node(function_id("shadow-summariser")).valid_to is None
    assert repo.get_node("cand:shadow-summariser").valid_to is None
    assert back.summary["resources_new"] == 1 and back.changes == ()
    assert ("cand:shadow-summariser", function_id("shadow-summariser")) in open_edges(
        repo, EdgeType.DERIVED_FROM
    )


def test_an_invalid_manifest_is_counted_and_the_run_goes_on(repo, clock, tmp_path):
    seeded(repo, clock)

    def break_one(raw):
        raw["manifests"].append({"Name": "/verity/manifests/bad.yaml", "Value": "system: [oops"})

    report = crawl_fixture(repo, clock, edited_fixture(tmp_path, break_one))
    assert report.manifests_invalid == 1 == report.summary["manifests_invalid"]
    assert dict((n, level) for n, level, _ in report.functions)["talent-screening"] is L.DECLARED


def test_a_fixture_run_is_all_simulated(repo, clock):
    seeded(repo, clock)
    crawl_fixture(repo, clock)
    owned = (
        NodeType.AWS_RESOURCE,
        NodeType.CANDIDATE,
        NodeType.DISCOVERY_RUN,
        NodeType.CHANGE_EVENT,
        NodeType.EVIDENCE,
    )
    for node_type in owned:
        assert {n.source for n in of_type(repo, node_type)} <= {Source.SIMULATED}, node_type
    crawler_edges = {
        EdgeType.RUNS_ON,
        EdgeType.ASSUMES,
        EdgeType.CALLS,
        EdgeType.OBSERVED,
        EdgeType.DERIVED_FROM,
        EdgeType.ABOUT,
        EdgeType.COLLECTED_FROM,
    }
    graph = repo.load_graph()
    sources = {
        d["record"].source
        for _, _, d in graph.edges(data=True)
        if d["record"].type in crawler_edges
    }
    assert sources == {Source.SIMULATED}
