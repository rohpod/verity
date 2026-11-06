"""Writes what the dashboard's tests compare against Python (ADR 0031, decisions 1, 4 and 12).

Run with: uv run python scripts/write_ui_fixtures.py [--mini-only]

1. `web/src/test/mini-snapshot.json`, `mini-expected.json` and `mini-audit.json` (committed): a
   small invented graph with a ChangeEvent, a discovered record and Evidence on both sides of the
   change, pushed through the export code, plus Python's `stale_by_change` and `audit_trail`
   answers for it. Its config Evidence is rebuilt by redaction, so the audit path crosses the ID
   map, which the recorded fixture's paths never do. A pytest checks that the files are current.
2. `web/.fixture/audit-parity.json` (git-ignored): Python's `audit_trail` for every requirement
   and scope of the recorded fixture. Redaction rebuilds 15 of 23 Evidence IDs and their hashes,
   so Python's answer is mapped to the published IDs through `Built.redacted.evidence_ids`. The
   dashboard never rewrites IDs.

Nothing here reads AWS.
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from verity_core.assess.apply import ApplyResult
from verity_core.content.loader import load_content
from verity_core.discovery.boundary import scrub
from verity_core.export.build import Built, build_snapshot, serialise
from verity_core.export.local import local_graph
from verity_core.graph.memory import InMemoryRepository
from verity_core.graph.traversals import audit_trail, stale_by_change
from verity_core.model import ids
from verity_core.model.edges import MapsToEdge, PlainEdge
from verity_core.model.enums import (
    AssuranceLevel,
    ControlKind,
    EdgeType,
    EvidenceKind,
    ImplementationStatus,
    NodeType,
    RationaleType,
    ScopeLevel,
    Source,
    StrmType,
    Sufficiency,
    SystemKind,
)
from verity_core.model.nodes import (
    AISystem,
    AWSResource,
    Candidate,
    ChangeEvent,
    Control,
    ControlAssessment,
    DiscoveryRun,
    Evidence,
    Framework,
    Organisation,
    Requirement,
)

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
FIXTURE = CONTENT / "fixtures" / "crawl" / "estate.json"
MINI_SNAPSHOT = ROOT / "web" / "src" / "test" / "mini-snapshot.json"
MINI_EXPECTED = ROOT / "web" / "src" / "test" / "mini-expected.json"
MINI_AUDIT = ROOT / "web" / "src" / "test" / "mini-audit.json"
AUDIT_PARITY = ROOT / "web" / ".fixture" / "audit-parity.json"
AS_OF = datetime(2026, 11, 6, tzinfo=UTC)
TENANT = "kestrel"
INVENTED_ACCOUNT = "123456789012"  # invented; redaction turns its digest into 000000000000


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


# --- 1. the invented mini graph ------------------------------------------------------------


def mini_graph():
    """Everything here is invented. One function, one resource, a change detected at 10:00, one
    config snapshot before it, one after it, and an attestation that was never collected from
    the resource. All three support one assessment."""
    common = {"tenant": TENANT}
    repo = InMemoryRepository(TENANT, lambda: AS_OF)
    org = Organisation(
        id=ids.organisation_id("mini"),
        name="Mini Org (invented)",
        source=Source.SYNTHETIC,
        **common,
    )
    system = AISystem(
        id=ids.system_id("mini-bot"),
        name="Mini Bot",
        purpose="An invented bot used by dashboard tests",
        kind=SystemKind.GENERATIVE_AI,
        source=Source.DECLARED,
        **common,
    )
    resource = AWSResource(
        id=ids.resource_id("lambda", "eu-north-1", "mini-bot"),
        resource_type="lambda",
        region="eu-north-1",
        name="mini-bot",
        env_var_names=["MINI_FLAG"],
        source=Source.DISCOVERED,
        **common,
    )
    control = Control(
        id=ids.control_id("VC-900"),
        title="Mini control (invented)",
        summary="An invented control for tests.",
        kind=ControlKind.TECHNICAL,
        automatable=True,
        scope_level=ScopeLevel.SYSTEM,
        source=Source.SEEDED,
        **common,
    )
    assessment = ControlAssessment(
        id=ids.ca_id(control.id, system.id),
        status=ImplementationStatus.IMPLEMENTED,
        assurance_level=AssuranceLevel.L2_EVIDENCED,
        method="config_snapshot",
        assessed_at=AS_OF,
        source=Source.DERIVED,
        **common,
    )
    run = DiscoveryRun(
        id=ids.discovery_run_id(AS_OF + timedelta(hours=10)),
        mode="full",
        started_at=AS_OF + timedelta(hours=10),
        finished_at=AS_OF + timedelta(hours=10, minutes=1),
        crawler_version="0.1.0",
        summary={"resources_changed": 1},
        source=Source.DISCOVERED,
        **common,
    )
    change = ChangeEvent(
        id=ids.change_event_id(run.id, resource.id),
        detected_at=AS_OF + timedelta(hours=10),
        source=Source.DISCOVERED,
        **common,
    )
    candidate = Candidate(
        id=ids.candidate_id("mini-summariser"),
        name="mini-summariser",
        ai_likelihood="probable",
        signals=["name_ai_token"],
        source=Source.DISCOVERED,
        **common,
    )
    framework = Framework(
        id=ids.framework_id("minifw"),
        name="Mini Framework (invented)",
        source_version="invented",
        source_url="https://example.invalid/minifw",
        last_verified=AS_OF.date(),
        binding=False,
        source=Source.SEEDED,
        **common,
    )
    requirement = Requirement(
        id=ids.requirement_id("minifw", "m1"),
        ref="M.1",
        summary="An invented requirement for tests.",
        source_url="https://example.invalid/minifw",
        source_version="invented",
        last_verified=AS_OF.date(),
        verified_against="primary_text",
        source=Source.SEEDED,
        **common,
    )
    config = {
        "config": {
            "architectures": ["arm64"],
            "code_sha256": "sha-of-mini-v1",
            "env_names": ["MINI_FLAG"],
            "handler": "app.handler",
            "memory_mb": 128,
            "role": f"arn:aws:iam::{scrub(INVENTED_ACCOUNT)}:role/mini-role",
            "runtime": "python3.12",
            "tags": {},
            "timeout_s": 10,
        }
    }

    def evidence(kind, at, content, source=Source.DISCOVERED):
        return Evidence.build(
            subject=resource.id,
            collector="crawler@0.1.0",
            collected_at=at,
            content=content,
            kind=kind,
            valid_until=at + timedelta(days=30),
            tenant=TENANT,
            source=source,
        )

    before = evidence(EvidenceKind.CONFIG_SNAPSHOT, AS_OF + timedelta(hours=9), config)
    after = evidence(
        EvidenceKind.CONFIG_SNAPSHOT,
        AS_OF + timedelta(hours=11),
        {"config": {**config["config"], "code_sha256": "sha-of-mini-v2"}},
    )
    signed = Evidence.build(
        subject=system.id,
        collector="person:mini-reviewer",
        collected_at=AS_OF + timedelta(hours=8),
        content={"decision_id": "attestation-mini", "statement": "An invented sign-off."},
        kind=EvidenceKind.ATTESTATION,
        valid_until=AS_OF + timedelta(days=30),
        tenant=TENANT,
        source=Source.SIMULATED,
    )
    for node in (
        org,
        system,
        resource,
        control,
        assessment,
        run,
        change,
        candidate,
        before,
        after,
        signed,
        framework,
        requirement,
    ):
        repo.upsert_node(node)

    def link(src, dst, kind, source=Source.DISCOVERED):
        repo.upsert_edge(PlainEdge(src=src, dst=dst, type=kind, tenant=TENANT, source=source))

    link(system.id, resource.id, EdgeType.RUNS_ON)
    link(run.id, resource.id, EdgeType.OBSERVED)
    link(change.id, resource.id, EdgeType.AFFECTS)
    link(candidate.id, resource.id, EdgeType.DERIVED_FROM)
    link(assessment.id, control.id, EdgeType.ASSESSES, Source.DERIVED)
    link(assessment.id, system.id, EdgeType.SCOPED_TO, Source.DERIVED)
    for item in (before, after):
        link(item.id, resource.id, EdgeType.COLLECTED_FROM)
        link(item.id, resource.id, EdgeType.ABOUT)
        link(item.id, assessment.id, EdgeType.SUPPORTS)
    link(requirement.id, framework.id, EdgeType.PART_OF, Source.SEEDED)
    repo.upsert_edge(
        MapsToEdge(
            src=requirement.id,
            dst=control.id,
            strm=StrmType.SUBSET_OF,
            strength=7,
            rationale_type=RationaleType.SEMANTIC,
            rationale="An invented mapping for tests.",
            sufficiency=Sufficiency.FULL,
            tenant=TENANT,
            source=Source.SEEDED,
        )
    )
    link(signed.id, system.id, EdgeType.ABOUT, Source.SIMULATED)
    link(signed.id, assessment.id, EdgeType.SUPPORTS, Source.SIMULATED)
    return repo.load_graph(), change.id


def _no_assessments_needed():
    """The mini graph holds no requirement to assess, so the staleness check is told there is
    nothing to write (as `built_from` does in the export tests)."""
    return patch(
        "verity_core.export.build.estimate_apply",
        return_value=ApplyResult(__import__("collections").Counter(), 0, (), (), ()),
    )


def mini_outputs() -> tuple[str, str, str]:
    graph, change_id = mini_graph()
    content = load_content(CONTENT)
    with _no_assessments_needed():
        built = build_snapshot(graph, content=content, as_of=AS_OF, data_source="fixture")
    impact = stale_by_change(graph, change_id)
    expected = {
        "change_id": impact.change_id,
        "evidence": [
            {
                "evidenceId": item.evidence_id,
                "resourceId": item.resource_id,
                "assessmentIds": list(item.assessment_ids),
            }
            for item in impact.evidence
        ],
        "assessment_ids": list(impact.assessment_ids),
    }
    # The mini snapshot is published through the same redaction, so IDs may have moved.
    mapped = built.redacted.evidence_ids
    for item in expected["evidence"]:
        item["evidenceId"] = mapped.get(item["evidenceId"], item["evidenceId"])
    audit = json.dumps(audit_parity(built, graph), indent=2, sort_keys=True) + "\n"
    return serialise(built.snapshot), json.dumps(expected, indent=2, sort_keys=True) + "\n", audit


# --- 2. audit-trail parity on the recorded fixture -----------------------------------------


def audit_parity(built: Built, graph) -> list[dict]:
    """Python's `audit_trail` for each requirement and scope, with Evidence mapped to the IDs and
    hashes the snapshot publishes. Everything else is unchanged by redaction."""
    published = {n.id: n for n in built.snapshot.nodes}
    id_map = built.redacted.evidence_ids

    def evidence(item):
        new_id = id_map.get(item.evidence_id, item.evidence_id)
        node = published[new_id]
        return {
            "evidenceId": new_id,
            "kind": item.kind.value,
            "collector": item.collector,
            "collectedAt": _stamp(item.collected_at),
            "validUntil": _stamp(item.valid_until),
            "sha256": node.sha256,
            "source": item.source.value,
        }

    requirements = sorted(n for n in graph if graph.nodes[n]["record"].type is NodeType.REQUIREMENT)
    scopes = sorted(
        n
        for n in graph
        if graph.nodes[n]["record"].type
        in (NodeType.AI_SYSTEM, NodeType.ORGANISATION, NodeType.PROVIDER)
    )
    rows = []
    for requirement in requirements:
        for scope in scopes:
            trail = audit_trail(graph, requirement, scope)
            rows.append(
                {
                    "requirement": requirement,
                    "scope": scope,
                    "links": [
                        {
                            "controlId": link.control_id,
                            "mapping": None
                            if link.mapping is None
                            else {
                                "strm": link.mapping.strm.value,
                                "strength": link.mapping.strength,
                                "sufficiency": link.mapping.sufficiency.value,
                            },
                            "resolution": link.resolution.value,
                            "providerId": link.provider_id,
                            "assessmentId": link.assessment_id,
                            "status": None if link.status is None else link.status.value,
                            "assuranceLevel": None
                            if link.assurance_level is None
                            else int(link.assurance_level),
                            "assessmentSource": None
                            if link.assessment_source is None
                            else link.assessment_source.value,
                            "assessedBy": link.assessed_by,
                            "signoffSource": None
                            if link.signoff_source is None
                            else link.signoff_source.value,
                            "evidence": [evidence(e) for e in link.evidence],
                        }
                        for link in trail.links
                    ],
                }
            )
    return rows


def write_audit_parity() -> int:
    content = load_content(CONTENT)
    graph = local_graph(content, FIXTURE, AS_OF)
    built = build_snapshot(graph, content=content, as_of=AS_OF, data_source="fixture")
    rows = audit_parity(built, graph)
    AUDIT_PARITY.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PARITY.write_text(
        json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return len(rows)


def main(argv: list[str]) -> int:
    snapshot, expected, audit = mini_outputs()
    MINI_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    MINI_SNAPSHOT.write_text(snapshot, encoding="utf-8")
    MINI_EXPECTED.write_text(expected, encoding="utf-8")
    MINI_AUDIT.write_text(audit, encoding="utf-8")
    print(f"wrote {MINI_SNAPSHOT.relative_to(ROOT)} and {MINI_EXPECTED.relative_to(ROOT)}")
    if "--mini-only" not in argv:
        print(f"wrote {write_audit_parity()} audit trails to {AUDIT_PARITY.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
