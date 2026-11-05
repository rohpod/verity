"""The repository against the real table: what moto cannot prove (ADR 0013, M3 notes)."""

import time
from datetime import timedelta
from uuid import uuid4

import pytest
from factories import evidence, make_edge
from live_support import PROBE_TENANT, live_only, probe_node, probe_repo, probe_session, utc_now
from verity_core.graph.errors import ConcurrentWriteError
from verity_core.model.enums import Direction, EdgeType, NodeType, Source
from verity_core.model.usage import UsageRecord

pytestmark = live_only

GSI_WAIT_SECONDS = 30


def test_nodes_edges_history_and_the_graph_round_trip():
    system, model = probe_node(NodeType.AI_SYSTEM), probe_node(NodeType.MODEL)
    with probe_session() as client:
        repo = probe_repo(client)
        stored = repo.upsert_node(system)
        repo.upsert_node(model)
        assert repo.get_node(system.id) == stored
        assert repo.upsert_node(system) == stored  # unchanged, so nothing is written

        changed = repo.upsert_node(system.model_copy(update={"purpose": "Changed"}))
        assert [v.version for v in repo.history(system.id)] == [1, 2]
        assert changed.version == 2

        edge = make_edge(EdgeType.USES_MODEL, system.id, model.id, tenant=PROBE_TENANT)
        repo.upsert_edge(edge)
        assert [e.dst for e in repo.neighbors(system.id, Direction.OUT)] == [model.id]
        assert [e.src for e in repo.neighbors(model.id, Direction.IN)] == [system.id]
        graph = repo.load_graph()
        assert set(graph.nodes) == {system.id, model.id}
        assert graph.number_of_edges() == 1

        repo.close_edge(system.id, EdgeType.USES_MODEL, model.id, valid_to=utc_now())
        assert repo.neighbors(system.id, Direction.OUT) == []
        assert repo.neighbors(model.id, Direction.IN) == []


def test_numbers_inside_evidence_survive_the_real_table():
    content = {"ratio": 0.1, "big": 12345678901234567890, "nested": {"f": 1.5e-7}}
    node = evidence(content=content, tenant=PROBE_TENANT)
    with probe_session() as client:
        repo = probe_repo(client)
        repo.upsert_node(node)
        stored = repo.get_node(node.id)
        assert stored.content == content and stored.sha256 == node.sha256


def test_usage_is_written_once_and_read_back_by_range():
    system = probe_node(NodeType.AI_SYSTEM)
    now = utc_now()
    record = UsageRecord(
        tenant=PROBE_TENANT,
        usage_id=uuid4(),
        system_id=system.id,
        provider_id="prov:mock-bedrock",
        model_id="model:fm-1",
        timestamp=now,
        token_estimate=120,
        source=Source.SIMULATED,
    )
    with probe_session() as client:
        repo = probe_repo(client)
        repo.append_usage(record)
        repo.append_usage(record)  # a retry meets its own item
        assert repo.usage_records(system.id) == [record]
        assert repo.usage_records(system.id, since=now + timedelta(seconds=1)) == []


def test_a_stale_write_is_refused_by_the_real_condition_check():
    system = probe_node(NodeType.AI_SYSTEM)
    with probe_session() as client:
        repo = probe_repo(client)
        stored = repo.upsert_node(system)
        with pytest.raises(ConcurrentWriteError):
            repo._write_node(stored, expected_version=99)


def test_how_long_a_new_node_takes_to_appear_in_the_type_index():
    node = probe_node(NodeType.AI_SYSTEM)
    with probe_session() as client:
        repo = probe_repo(client)
        repo.upsert_node(node)
        started = time.monotonic()
        while time.monotonic() - started < GSI_WAIT_SECONDS:
            if repo.nodes_by_type(NodeType.AI_SYSTEM):
                print(f"\nRESULT gsi delay: {time.monotonic() - started:.3f} s")
                return
            time.sleep(0.05)
        pytest.fail(f"not in the index after {GSI_WAIT_SECONDS} s")
