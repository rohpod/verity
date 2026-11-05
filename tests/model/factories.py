"""Valid example of every node type, shared by the model tests. All data is fictional."""

from datetime import UTC, date, datetime

from verity_core.model import ids
from verity_core.model.enums import (
    AiLikelihood,
    AssuranceLevel,
    ControlKind,
    DataClassification,
    EvidenceKind,
    ImplementationStatus,
    ModelOrigin,
    NodeType,
    RunMode,
    ScopeLevel,
    Source,
    SystemKind,
)
from verity_core.model.evidence import Evidence
from verity_core.model.nodes import (
    AISystem,
    AWSResource,
    Candidate,
    ChangeEvent,
    Control,
    ControlAssessment,
    Dataset,
    Department,
    DiscoveryRun,
    Framework,
    Model,
    Organisation,
    Person,
    Policy,
    Provider,
    Requirement,
    Risk,
)

TENANT = "kestrel"
T0 = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
COMMON = {"tenant": TENANT, "source": Source.SYNTHETIC}


def evidence(**overrides) -> Evidence:
    fields = {
        "subject": ids.resource_id("lambda", "eu-north-1", "support-assistant"),
        "collector": "crawler@0.1.0",
        "collected_at": T0,
        "valid_until": datetime(2026, 12, 5, tzinfo=UTC),
        "kind": EvidenceKind.CONFIG_SNAPSHOT,
        "content": {"runtime": "python3.12"},
        **COMMON,
    } | overrides
    return Evidence.build(**fields)


def one_of_each() -> dict[NodeType, object]:
    """One valid node per node type."""
    nodes = [
        Organisation(id=ids.organisation_id("kestrel"), name="Kestrel Cloud Ltd", **COMMON),
        Department(id=ids.department_id("people"), name="People", **COMMON),
        Person(id=ids.person_id("a-singh"), name="Asha Singh", job_title="Head of HR", **COMMON),
        AISystem(
            id=ids.system_id("talent-screening"),
            name="Talent Screening",
            purpose="Rank job applicants for recruiters",
            kind=SystemKind.CLASSICAL_ML,
            **COMMON,
        ),
        Candidate(
            id=ids.candidate_id("shadow-summariser"),
            name="shadow-summariser",
            ai_likelihood=AiLikelihood.PROBABLE,
            signals=["env_var:OPENAI_BASE_URL"],
            **COMMON,
        ),
        AWSResource(
            id=ids.resource_id("lambda", "eu-north-1", "shadow-summariser"),
            resource_type="lambda",
            region="eu-north-1",
            name="shadow-summariser",
            env_var_names=["OPENAI_BASE_URL"],
            **COMMON,
        ),
        Model(
            id=ids.model_id("screening-lr"),
            name="Screening logistic regression",
            origin=ModelOrigin.IN_HOUSE,
            **COMMON,
        ),
        Provider(
            id=ids.provider_id("mock-openai"), name="OpenAI (simulated)", simulated=True, **COMMON
        ),
        Dataset(
            id=ids.dataset_id("applicants"),
            name="Applicant profiles",
            classification=DataClassification.RESTRICTED,
            personal_data=True,
            **COMMON,
        ),
        Risk(
            id=ids.risk_id("screening-bias"),
            title="Biased ranking",
            description="Test only",
            **COMMON,
        ),
        Control(
            id=ids.control_id("VC-014"),
            title="Human oversight",
            summary="A person can review and override outputs.",
            kind=ControlKind.ORGANISATIONAL,
            automatable=False,
            scope_level=ScopeLevel.SYSTEM,
            **COMMON,
        ),
        ControlAssessment(
            id=ids.ca_id(ids.control_id("VC-014"), ids.system_id("talent-screening")),
            status=ImplementationStatus.PARTIALLY_IMPLEMENTED,
            assurance_level=AssuranceLevel.L2_EVIDENCED,
            **COMMON,
        ),
        Requirement(
            id=ids.requirement_id("euaia", "art50-1"),
            ref="Art. 50(1)",
            summary="Test fixture, not verified content.",
            source_url="https://example.invalid/test-fixture",
            version="test fixture",
            last_verified=date(2026, 11, 5),
            **COMMON,
        ),
        Framework(
            id=ids.framework_id("euaia"),
            name="EU AI Act (test fixture)",
            version="test fixture",
            source_url="https://example.invalid/test-fixture",
            last_verified=date(2026, 11, 5),
            **COMMON,
        ),
        evidence(),
        Policy(id=ids.policy_id("ai-policy"), title="AI policy", summary="Test only", **COMMON),
        DiscoveryRun(
            id=ids.make_id(NodeType.DISCOVERY_RUN, "2026-11-05T09-00"),
            mode=RunMode.FULL,
            started_at=T0,
            crawler_version="0.1.0",
            **COMMON,
        ),
        ChangeEvent(
            id=ids.make_id(NodeType.CHANGE_EVENT, "support-assistant-1"),
            detected_at=T0,
            previous_config_hash="a" * 64,
            new_config_hash="b" * 64,
            **COMMON,
        ),
    ]
    return {node.type: node for node in nodes}


def make_edge(edge_type, src, dst, **overrides):
    """A valid edge of any type between two node IDs, supplying the type's own fields."""
    from verity_core.model.edges import AppliesToEdge, MapsToEdge, PlainEdge, ProcessesEdge
    from verity_core.model.enums import (
        EdgeType,
        Purpose,
        RationaleType,
        Role,
        StrmType,
        Sufficiency,
    )

    fields = {"src": src, "dst": dst, "type": edge_type, **COMMON}
    match edge_type:
        case EdgeType.MAPS_TO:
            cls, extra = (
                MapsToEdge,
                {
                    "strm": StrmType.SUBSET_OF,
                    "strength": 7,
                    "rationale_type": RationaleType.FUNCTIONAL,
                    "rationale": "Test fixture, not a verified mapping.",
                    "sufficiency": Sufficiency.FULL,
                },
            )
        case EdgeType.APPLIES_TO:
            cls, extra = (
                AppliesToEdge,
                {
                    "role": Role.DEPLOYER,
                    "rule_id": "test-rule",
                    "reason": "Test fixture.",
                },
            )
        case EdgeType.PROCESSES:
            cls, extra = ProcessesEdge, {"purpose": Purpose.INFERENCE}
        case _:
            cls, extra = PlainEdge, {}
    return cls(**fields | extra | overrides)


def rule_nodes() -> dict[NodeType, object]:
    """One node per type for sweeping edge rules. The Model is third-party and the AWSResource
    an IAM role, so only the endpoint-type rule can fail."""
    nodes = one_of_each()
    nodes[NodeType.MODEL] = nodes[NodeType.MODEL].model_copy(
        update={"origin": ModelOrigin.THIRD_PARTY}
    )
    nodes[NodeType.AWS_RESOURCE] = AWSResource(
        id=ids.resource_id("iam-role", "global", "crawler"),
        resource_type="iam-role",
        region="global",
        name="crawler",
        **COMMON,
    )
    return nodes


def twin(node):
    """A second node of the same type, for edges between two nodes of one type."""
    return node.model_copy(update={"id": ids.make_id(node.type, "twin")})
