from datetime import UTC, datetime, timedelta

import boto3
import pytest
from content_samples import broken, good_files, requirement, write_tree
from factories import TENANT
from moto import mock_aws
from verity_core.content.loader import load_content
from verity_core.content.seed import estimate, seed
from verity_core.graph.dynamodb.repository import DynamoDBRepository
from verity_core.graph.dynamodb.table import table_definition
from verity_core.graph.integrity import check_integrity
from verity_core.graph.memory import InMemoryRepository
from verity_core.model.enums import NodeType

START = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture(params=["memory", "dynamodb"])
def repo(request, clock):
    if request.param == "memory":
        yield InMemoryRepository(TENANT, clock)
        return
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-north-1")
        client.create_table(**table_definition())
        yield DynamoDBRepository(TENANT, clock, client=client)


def load(tmp_path, files=None):
    return load_content(write_tree(tmp_path, files or good_files()), tenant=TENANT)


def test_the_first_seed_writes_everything(repo, clock, tmp_path):
    content = load(tmp_path)
    report = seed(repo, content, clock)
    assert report.nodes_written == len(content.nodes())
    assert report.edges_written == len(content.edges)
    assert report.nodes_unchanged == report.edges_unchanged == 0
    assert len(repo.nodes_by_type(NodeType.REQUIREMENT)) == 8
    assert len(repo.nodes_by_type(NodeType.CONTROL)) == 4


def test_the_seeded_graph_is_sound(repo, clock, tmp_path):
    seed(repo, load(tmp_path), clock)
    assert check_integrity(repo.load_graph()) == []


def test_seeding_twice_changes_nothing(repo, clock, tmp_path):
    content = load(tmp_path)
    seed(repo, content, clock)
    before = {n.id: n.version for n in repo.nodes_by_type(NodeType.REQUIREMENT)}

    clock.now += timedelta(minutes=5)
    again = seed(repo, content, clock)

    assert again.written == 0
    assert again.nodes_unchanged == len(content.nodes())
    assert again.edges_unchanged == len(content.edges)
    nodes = repo.nodes_by_type(NodeType.REQUIREMENT)
    assert {n.id: n.version for n in nodes} == before
    assert all(len(repo.history(n.id)) == 1 for n in nodes)  # no new H# entry (D14)


def test_a_changed_record_is_the_only_one_written(repo, clock, tmp_path):
    seed(repo, load(tmp_path / "a"), clock)

    def edit(files):
        requirement(files, "euaia", "art4")["summary"] = "A reworded summary of the duty."

    clock.now += timedelta(minutes=5)
    report = seed(repo, load(tmp_path / "b", broken(edit)), clock)

    assert (report.nodes_written, report.edges_written) == (1, 0)
    changed = repo.get_node("req:euaia:art4")
    assert changed.version == 2
    assert len(repo.history("req:euaia:art4")) == 2


def test_progress_is_reported_for_every_record(repo, clock, tmp_path):
    content = load(tmp_path)
    calls = []
    seed(repo, content, clock, lambda what, done, total: calls.append((what, done, total)))
    nodes, edges = len(content.nodes()), len(content.edges)
    assert len(calls) == nodes + edges
    assert calls[0] == ("nodes", 1, nodes)
    assert calls[nodes - 1] == ("nodes", nodes, nodes)
    assert calls[-1] == ("edges", edges, edges)


def test_the_estimate_uses_the_measured_write_costs(tmp_path):
    content = load(tmp_path)
    plan = estimate(content)
    nodes, edges = len(content.nodes()), len(content.edges)
    assert (plan.nodes, plan.edges) == (nodes, edges)
    assert plan.table_units == 4 * (nodes + edges)
    assert plan.index_units == nodes
    assert plan.seconds == plan.table_units / 15


def test_the_estimate_at_the_design_target_is_about_six_minutes():
    from verity_core.content.seed import SeedEstimate

    plan = SeedEstimate(nodes=300, edges=1000, table_units=5200, index_units=300)
    assert round(plan.seconds / 60) == 6
