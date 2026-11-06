"""The live collector's path through `crawl`, against moto and a stub for CloudTrail."""

from contextlib import nullcontext
from datetime import timedelta

from discovery_support import (
    CANARY,
    MINI,
    MOTO_ACCOUNT,
    aws_collector,
    dump,
    of_type,
    populate_moto,
    seeded,
    table_text,
)
from moto import mock_aws
from verity_core.discovery.pipeline import crawl
from verity_core.graph.memory import InMemoryRepository
from verity_core.model.enums import EdgeType, NodeType, Source


def moto_context(repo):
    """The DynamoDB fixture already runs inside `mock_aws`; the in-memory one does not."""
    return mock_aws() if isinstance(repo, InMemoryRepository) else nullcontext()


def test_a_moto_account_is_crawled_discovered_and_clean(repo, clock, capsys, caplog):
    with moto_context(repo):
        populate_moto(tags={"ai:system-id": "sys:lead-scoring"})
        seeded(repo, clock)
        collector = aws_collector(clock)
        report = crawl(repo, MINI, collector, clock)
        clock.advance(hours=1)
        again = crawl(repo, MINI, collector, clock)

    assert again.written.most_common() == [("runs", 1)]
    assert {n: level.value for n, level, _ in report.functions} == {"shadow-summariser": "declared"}
    owned = (
        NodeType.AWS_RESOURCE,
        NodeType.DISCOVERY_RUN,
        NodeType.EVIDENCE,
    )
    for node_type in owned:
        nodes = of_type(repo, node_type)
        assert nodes and {n.source for n in nodes} == {Source.DISCOVERED}, node_type
    graph = repo.load_graph()
    crawler = {EdgeType.RUNS_ON, EdgeType.ASSUMES, EdgeType.OBSERVED, EdgeType.COLLECTED_FROM}
    sources = {
        d["record"].source for _, _, d in graph.edges(data=True) if d["record"].type in crawler
    }
    assert sources == {Source.DISCOVERED}

    out = capsys.readouterr()
    everything = "\n".join(
        [dump(repo), table_text(repo), out.out, out.err, caplog.text, repr(report), repr(again)]
    )
    assert CANARY not in everything
    assert MOTO_ACCOUNT not in everything
    assert "<account>" in everything


def test_cloudtrail_is_read_for_the_lookback_window(repo, clock):
    from discovery_support import StubCloudTrail, trail_event

    trail = StubCloudTrail([trail_event("shadow-role", name="InvokeModel")])
    with moto_context(repo):
        populate_moto()
        seeded(repo, clock)
        report = crawl(repo, MINI, aws_collector(clock, trail=trail), clock)
    (call,) = trail.calls
    assert call["EndTime"] - call["StartTime"] == timedelta(days=90)
    levels = {n: (level.value, signals) for n, level, signals in report.functions}
    assert "trail_ai_event" in levels["shadow-summariser"][1]
    assert report.summary["trail_events"] == 1
