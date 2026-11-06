"""Helpers for the export tests. Everything here is invented."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from verity_core.content.loader import load_content
from verity_core.discovery.boundary import scrub
from verity_core.export.build import build_snapshot
from verity_core.export.local import local_graph
from verity_core.graph.memory import InMemoryRepository
from verity_core.model import ids
from verity_core.model.edges import PlainEdge
from verity_core.model.enums import (
    AssuranceLevel,
    EdgeType,
    EvidenceKind,
    ImplementationStatus,
    NodeType,
    Source,
)
from verity_core.model.nodes import AWSResource, ControlAssessment, Evidence

ROOT = Path(__file__).parents[2]
CONTENT = ROOT / "content"
FIXTURE = CONTENT / "fixtures" / "crawl" / "estate.json"
AS_OF = datetime(2026, 11, 6, tzinfo=UTC)
TENANT = "kestrel"
OWN_NUMBER = "111122223333"  # invented
OTHER_NUMBER = "444455556666"  # invented
THIRD_NUMBER = "777788889999"  # invented
OWN, OTHER, THIRD = scrub(OWN_NUMBER), scrub(OTHER_NUMBER), scrub(THIRD_NUMBER)
COMMON = {"tenant": TENANT, "source": Source.DISCOVERED}


def clock() -> datetime:
    return AS_OF


def evidence(subject: str, content: dict, *, at: datetime = AS_OF) -> Evidence:
    return Evidence.build(
        subject=subject,
        collector="crawler@0.1.0",
        collected_at=at,
        content=content,
        kind=EvidenceKind.CONFIG_SNAPSHOT,
        valid_until=at + timedelta(days=30),
        **COMMON,
    )


def function_config(role_digest: str, *extra: str) -> dict:
    """Shaped like a crawler `config_snapshot` of a Lambda function."""
    return {
        "config": {
            "role": f"arn:aws:iam::{role_digest}:role/some-role",
            "policies": [{"statements": [{"resources": list(extra)}]}],
        },
        "config_hash": "a" * 64,
    }


def small_graph(*contents: dict, extra_edges: bool = True):
    """One AWSResource per content, one Evidence about it, and one assessment each supports."""
    repo = InMemoryRepository(TENANT, clock)
    made = []
    for position, content in enumerate(contents):
        resource_id = ids.make_id(NodeType.AWS_RESOURCE, "lambda", f"fn-{position}")
        repo.upsert_node(
            AWSResource(
                id=resource_id,
                resource_type="lambda",
                region="eu-north-1",
                name=f"fn-{position}",
                config_hash="b" * 64,
                **COMMON,
            )
        )
        item = evidence(resource_id, content, at=AS_OF + timedelta(minutes=position))
        repo.upsert_node(item)
        made.append((resource_id, item))
        if extra_edges:
            repo.upsert_edge(PlainEdge(src=item.id, dst=resource_id, type=EdgeType.ABOUT, **COMMON))
    if extra_edges and made:
        assessment = ControlAssessment(
            id=ids.ca_id("ctl:VC-060", "org:kestrel"),
            status=ImplementationStatus.NOT_ASSESSED,
            assurance_level=AssuranceLevel.L0_INFERRED,
            **COMMON,
        )
        # The scope and control nodes are not needed by the snapshot, only the references.
        repo.upsert_node(assessment)
        for _, item in made:
            repo.upsert_edge(
                PlainEdge(src=item.id, dst=assessment.id, type=EdgeType.SUPPORTS, **COMMON)
            )
    return repo.load_graph(), made


def built_from(graph, **kw):
    return build_snapshot(graph, as_of=AS_OF, data_source="fixture", **kw)


_FIXTURE_GRAPH = None


def fixture_graph():
    """The recorded estate, crawled and assessed in memory. Built once."""
    global _FIXTURE_GRAPH
    if _FIXTURE_GRAPH is None:
        _FIXTURE_GRAPH = local_graph(load_content(CONTENT), FIXTURE, AS_OF)
    return _FIXTURE_GRAPH
