"""Small invented graphs for the assessment tests. Everything here is fictional."""

from datetime import UTC, date, datetime, timedelta

from verity_core.assess.controls import ControlAssessor
from verity_core.assess.findings import derive_findings
from verity_core.assess.requirements import requirement_statuses
from verity_core.graph.loader import build_graph
from verity_core.model import ids
from verity_core.model.edges import AppliesToEdge, MapsToEdge, PlainEdge
from verity_core.model.enums import (
    ControlKind,
    EdgeType,
    EvidenceKind,
    ModelOrigin,
    RationaleType,
    Role,
    ScopeLevel,
    Source,
    StrmType,
    Sufficiency,
    SystemKind,
    VerifiedAgainst,
)
from verity_core.model.evidence import Evidence
from verity_core.model.nodes import (
    AISystem,
    AWSResource,
    ChangeEvent,
    Control,
    Framework,
    Model,
    Organisation,
    Person,
    Provider,
    Requirement,
)

TENANT = "kestrel"
COMMON = {"tenant": TENANT, "source": Source.SYNTHETIC}
AS_OF = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
ORG = "org:kestrel"
SYS = "sys:s"
PROV = "prov:p"
PERSON = "person:l-ivanova"
EARLIER = AS_OF - timedelta(days=10)
LATER_VALID = AS_OF + timedelta(days=60)


def control(code, *, kind=ControlKind.ORGANISATIONAL, automatable=False, scope=ScopeLevel.SYSTEM):
    return Control(
        id=ids.control_id(code),
        title=code,
        summary="Invented for the tests.",
        kind=kind,
        automatable=automatable,
        scope_level=scope,
        **COMMON,
    )


def technical(code, **kw):
    return control(code, kind=ControlKind.TECHNICAL, automatable=True, **kw)


def requirement(slug, framework="euaia"):
    return Requirement(
        id=ids.requirement_id(framework, slug),
        ref=slug,
        summary="Invented for the tests.",
        source_url="https://example.invalid/x",
        source_version="test",
        last_verified=date(2026, 11, 5),
        verified_against=VerifiedAgainst.PRIMARY_TEXT,
        **COMMON,
    )


def req_id(slug, framework="euaia"):
    return ids.requirement_id(framework, slug)


def maps(req, code, strm=StrmType.SUBSET_OF, sufficiency=Sufficiency.FULL, strength=8):
    none = strm is StrmType.NO_RELATIONSHIP
    return MapsToEdge(
        src=req_id(req),
        dst=ids.control_id(code),
        strm=strm,
        strength=None if none else strength,
        rationale_type=RationaleType.SEMANTIC,
        rationale="Invented for the tests.",
        sufficiency=None if none else sufficiency,
        **COMMON,
    )


def applies(req, target=SYS, role=Role.PROVIDER, in_force_from=None, condition=None):
    return AppliesToEdge(
        src=req_id(req),
        dst=target,
        role=role,
        rule_id="test-rule",
        reason="Invented for the tests.",
        in_force_from=in_force_from,
        condition=condition,
        **{**COMMON, "source": Source.DERIVED},
    )


def evidence(
    code,
    kind,
    *,
    scope=SYS,
    collector=PERSON,
    collected_at=EARLIER,
    valid_until=LATER_VALID,
    source=Source.SYNTHETIC,
    subject=None,
    **content,
):
    return Evidence.build(
        subject=subject or scope,
        collector=collector,
        collected_at=collected_at,
        valid_until=valid_until,
        kind=kind,
        content={"control": ids.control_id(code), "scope": scope, **content},
        tenant=TENANT,
        source=source,
    )


def verification(code, status="implemented", **kw):
    return evidence(
        code,
        EvidenceKind.ATTESTATION,
        decision_kind="verification",
        status=status,
        **kw,
    )


def attestation(code, status="implemented", **kw):
    return evidence(
        code, EvidenceKind.ATTESTATION, decision_kind="attestation", status=status, **kw
    )


def automated_result(code, outcome, **kw):
    return evidence(
        code,
        EvidenceKind.AUTOMATED_TEST,
        collector="crawler@0.1.0",
        outcome=outcome,
        **kw,
    )


def world(
    *,
    controls=(),
    requirements=(),
    mappings=(),
    applications=(),
    evidence_items=(),
    models=("in_house",),
    owner=True,
    extra_nodes=(),
    extra_edges=(),
    framework="euaia",
    binding=True,
):
    """An organisation, one system `sys:s` using the given models, and what the test adds.

    `models` is a tuple of "in_house", "known" (third party, provider `prov:p`) or
    "unknown" (third party, no provider).
    """
    nodes = [
        Organisation(id=ORG, name="Kestrel Cloud Ltd", **COMMON),
        AISystem(id=SYS, name="S", purpose="Invented", kind=SystemKind.CLASSICAL_ML, **COMMON),
        Person(id=PERSON, name="L", job_title="Head of Legal", **COMMON),
        Framework(
            id=ids.framework_id(framework),
            name="F",
            source_version="test",
            source_url="https://example.invalid/f",
            last_verified=date(2026, 11, 5),
            binding=binding,
            **COMMON,
        ),
        Provider(
            id=PROV, name="P (simulated)", simulated=True, **{**COMMON, "source": Source.SIMULATED}
        ),
        *controls,
        *(requirement(r, framework) for r in requirements),
        *evidence_items,
        *extra_nodes,
    ]
    edges = list(mappings) + list(applications) + list(extra_edges)
    if owner:
        edges.append(PlainEdge(src=PERSON, dst=SYS, type=EdgeType.OWNS, **COMMON))
    for n, kind in enumerate(models):
        model_id = ids.model_id(f"m{n}")
        origin = ModelOrigin.IN_HOUSE if kind == "in_house" else ModelOrigin.THIRD_PARTY
        nodes.append(Model(id=model_id, name=f"m{n}", origin=origin, **COMMON))
        edges.append(PlainEdge(src=SYS, dst=model_id, type=EdgeType.USES_MODEL, **COMMON))
        if kind == "known":
            edges.append(PlainEdge(src=model_id, dst=PROV, type=EdgeType.PROVIDED_BY, **COMMON))
    return build_graph(nodes, edges)


def status_of(graph, req, as_of=AS_OF):
    assessor = ControlAssessor(graph, as_of)
    found = {s.requirement_id: s for s in requirement_statuses(graph, SYS, assessor)}
    return found[req_id(req)]


def findings_of(graph, as_of=AS_OF, extra=()):
    assessor = ControlAssessor(graph, as_of)
    statuses = requirement_statuses(graph, SYS, assessor)
    return derive_findings(graph, as_of, assessor.results(), statuses, extra)


RESOURCE = ids.resource_id("lambda", "eu-north-1", "fn")


def resource_and_change(detected_at, collected_ev: Evidence):
    """A Lambda, a change detected on it, and the evidence recorded as collected from it."""
    resource = AWSResource(
        id=RESOURCE, resource_type="lambda", region="eu-north-1", name="fn", **COMMON
    )
    event = ChangeEvent(id="chg:c", detected_at=detected_at, **COMMON)
    nodes = [resource, event]
    edges = [
        PlainEdge(src=event.id, dst=RESOURCE, type=EdgeType.AFFECTS, **COMMON),
        PlainEdge(src=collected_ev.id, dst=RESOURCE, type=EdgeType.COLLECTED_FROM, **COMMON),
    ]
    return nodes, edges
