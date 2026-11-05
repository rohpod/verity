"""A small fictional estate covering the three use cases (architecture section C), loaded
through a repository so every write is validated.

Everything here is synthetic test data for Kestrel Cloud Ltd. Requirement summaries, mappings
and strengths are placeholders marked "test fixture": M4 owns the real content, and nothing
here is verified legal or ISO text. Mock providers and the demo sign-off use `source=simulated`
(D11), and nothing is ever invoked.
"""

from datetime import date, timedelta

from factories import COMMON, T0, TENANT, evidence, make_edge
from verity_core.model import ids
from verity_core.model.enums import (
    AssuranceLevel,
    ControlKind,
    EdgeType,
    EvidenceKind,
    ImplementationStatus,
    ModelOrigin,
    NodeType,
    RationaleType,
    Role,
    ScopeLevel,
    Source,
    StrmType,
    Sufficiency,
    SystemKind,
)
from verity_core.model.nodes import (
    AISystem,
    AWSResource,
    ChangeEvent,
    Control,
    ControlAssessment,
    Framework,
    Model,
    Organisation,
    Person,
    Provider,
    Requirement,
    Risk,
)

SIMULATED = {"tenant": TENANT, "source": Source.SIMULATED}
NOTE = "Test fixture, not verified content."

# --- IDs -----------------------------------------------------------------------------------
ORG = ids.organisation_id("kestrel")
VERIFIER = ids.person_id(
    "l-ivanova"
)  # Head of Legal: owns Contract Insights, verifies Talent oversight
HR_LEAD = ids.person_id("a-singh")  # owns Talent Screening
SUPPORT_LEAD = ids.person_id("m-okafor")  # owns Support Assistant

SUPPORT = ids.system_id("support-assistant")
TALENT = ids.system_id("talent-screening")
CONTRACT = ids.system_id("contract-insights")

RES_SUPPORT = ids.resource_id("lambda", "eu-north-1", "support-assistant")
RES_TALENT = ids.resource_id("lambda", "eu-north-1", "talent-screening")
RES_CONTRACT = ids.resource_id("lambda", "eu-north-1", "contract-insights")
RISK_SUPPORT = ids.risk_id("chatbot-misinformation")
RISK_TALENT = ids.risk_id("screening-bias")
RISK_CONTRACT = ids.risk_id("vendor-data-transfer")
CHG_SUPPORT = ids.make_id(NodeType.CHANGE_EVENT, "support-assistant-1")
CHG_TALENT = ids.make_id(NodeType.CHANGE_EVENT, "talent-screening-1")
CHG_CONTRACT = ids.make_id(NodeType.CHANGE_EVENT, "contract-insights-1")
CHANGE_DETECTED_AT = T0 + timedelta(days=1)

BEDROCK = ids.provider_id("mock-bedrock")
OPENAI = ids.provider_id("mock-openai")

EUAIA = ids.framework_id("euaia")
ISO = ids.framework_id("iso42001")


def req(framework: str, ref: str) -> str:
    return ids.requirement_id(framework, ref)


ART4 = req("euaia", "art4")  # organisation-level
ART9 = req("euaia", "art9")  # parent, with no mapping of its own
ART9_2A = req("euaia", "art9-2a")  # sub-clause of ART9
ART14 = req("euaia", "art14")
ART25 = req("euaia", "art25")  # only a no_relationship mapping, aimed at no one
ART50_1 = req("euaia", "art50-1")
ISO_A6 = req("iso42001", "A.6")
ISO_A6_2_4 = req("iso42001", "A.6.2.4")  # sub-clause of ISO_A6
ISO_A8_2 = req("iso42001", "A.8.2")
ISO_A9 = req("iso42001", "A.9")
ISO_A9_3 = req("iso42001", "A.9.3")  # sub-clause of ISO_A9
ISO_A10_3 = req("iso42001", "A.10.3")
ISO_A7_4 = req("iso42001", "A.7.4")

VC_AI_LITERACY = ids.control_id("VC-001")  # organisation level
VC_DISCLOSURE = ids.control_id("VC-012")  # technical and automatable
VC_OVERSIGHT = ids.control_id("VC-014")
VC_BIAS_TEST = ids.control_id("VC-021")
VC_SUPPLIER_DPA = ids.control_id("VC-030")  # provider level
VC_EGRESS = ids.control_id("VC-041")  # technical and automatable


def ca(control: str, scope: str) -> str:
    return ids.ca_id(control, scope)


def _requirement(framework: str, ref: str, label: str) -> Requirement:
    return Requirement(
        id=req(framework, ref),
        ref=label,
        summary=NOTE,
        source_url="https://example.invalid/test-fixture",
        source_version="test fixture",
        last_verified=date(2026, 11, 5),
        **COMMON,
    )


def _control(code, title, kind, scope_level, *, automatable=False) -> Control:
    return Control(
        id=ids.control_id(code),
        title=title,
        summary=NOTE,
        kind=kind,
        automatable=automatable,
        scope_level=scope_level,
        **COMMON,
    )


def _assessment(control, scope, status, level, *, source=Source.SYNTHETIC, assessor=None):
    return ControlAssessment(
        id=ca(control, scope),
        status=status,
        assurance_level=level,
        method="test fixture",
        assessed_at=T0,
        assessor=assessor,
        tenant=TENANT,
        source=source,
    )


def _map(requirement, control, strm, strength, sufficiency):
    return make_edge(
        EdgeType.MAPS_TO,
        requirement,
        control,
        strm=strm,
        strength=strength,
        sufficiency=sufficiency,
        rationale_type=RationaleType.FUNCTIONAL,
        rationale=NOTE,
    )


def _applies(requirement, target, role, rule_id):
    return make_edge(
        EdgeType.APPLIES_TO, requirement, target, role=role, rule_id=rule_id, reason=NOTE
    )


def _evidence(subject, collector, kind, *, source=Source.SYNTHETIC, **content):
    return evidence(
        subject=subject,
        collector=collector,
        kind=kind,
        source=source,
        valid_until=T0 + timedelta(days=30),
        **content,
    )


def load_estate(repo) -> None:
    """Write nodes first, then edges, as the repository requires."""
    subset, full, partial = StrmType.SUBSET_OF, Sufficiency.FULL, Sufficiency.PARTIAL
    disclosure_test = _evidence(
        SUPPORT, "crawler@0.1.0", EvidenceKind.AUTOMATED_TEST, content={"banner_shown": True}
    )
    oversight_signoff = _evidence(
        TALENT,
        VERIFIER,
        EvidenceKind.ATTESTATION,
        source=Source.SIMULATED,
        content={"statement": "simulated sign-off"},
    )
    # A crawler snapshot of the Talent Screening function. It supports the same assessment as
    # the person's attestation, but only the snapshot was collected from the resource.
    talent_config = _evidence(
        TALENT,
        "crawler@0.1.0",
        EvidenceKind.CONFIG_SNAPSHOT,
        content={"human_review_enabled": True},
        collected_at=T0 - timedelta(days=1),
    )
    # Contract Insights' own control. Its DPA gap with the provider is a separate assessment.
    contract_config = _evidence(
        CONTRACT,
        "crawler@0.1.0",
        EvidenceKind.CONFIG_SNAPSHOT,
        content={"egress_allowlist": ["mock-openai"]},
        collected_at=T0 - timedelta(days=1),
    )
    contract_transfer_record = _evidence(
        CONTRACT,
        VERIFIER,
        EvidenceKind.DOCUMENT_REF,
        content=None,
        content_ref="evidence/transfer-record-contract-insights.md",
        file_sha256="e" * 64,
    )
    bedrock_dpa = _evidence(
        BEDROCK,
        VERIFIER,
        EvidenceKind.DOCUMENT_REF,
        content=None,
        content_ref="evidence/dpa-mock-bedrock.md",
        file_sha256="d" * 64,
    )

    nodes = [
        Organisation(id=ORG, name="Kestrel Cloud Ltd", **COMMON),
        Person(id=VERIFIER, name="Lena Ivanova", job_title="Head of Legal", **COMMON),
        Person(id=HR_LEAD, name="Asha Singh", job_title="Head of People", **COMMON),
        Person(id=SUPPORT_LEAD, name="Mateo Okafor", job_title="Support Lead", **COMMON),
        *(
            AWSResource(id=res_id, resource_type="lambda", region="eu-north-1", name=name, **COMMON)
            for res_id, name in (
                (RES_SUPPORT, "support-assistant"),
                (RES_TALENT, "talent-screening"),
                (RES_CONTRACT, "contract-insights"),
            )
        ),
        *(
            Risk(id=risk_id, title=title, description=NOTE, **COMMON)
            for risk_id, title in (
                (RISK_SUPPORT, "Chatbot gives wrong answers"),
                (RISK_TALENT, "Ranking is biased"),
                (RISK_CONTRACT, "Contract data leaves the EU"),
            )
        ),
        *(
            ChangeEvent(id=chg_id, detected_at=CHANGE_DETECTED_AT, **COMMON)
            for chg_id in (CHG_SUPPORT, CHG_TALENT, CHG_CONTRACT)
        ),
        AISystem(
            id=SUPPORT,
            name="Support Assistant",
            purpose="Answer customer support questions",
            kind=SystemKind.GENERATIVE_AI,
            **COMMON,
        ),
        AISystem(
            id=TALENT,
            name="Talent Screening",
            purpose="Rank job applicants for recruiters",
            kind=SystemKind.CLASSICAL_ML,
            **COMMON,
        ),
        AISystem(
            id=CONTRACT,
            name="Contract Insights",
            purpose="Summarise customer contracts",
            kind=SystemKind.EXTERNAL_AI_API,
            **COMMON,
        ),
        Provider(id=BEDROCK, name="Bedrock (simulated)", simulated=True, **SIMULATED),
        Provider(id=OPENAI, name="OpenAI (simulated)", simulated=True, **SIMULATED),
        Model(
            id=ids.model_id("bedrock-fm"),
            name="Bedrock FM",
            origin=ModelOrigin.THIRD_PARTY,
            **SIMULATED,
        ),
        Model(
            id=ids.model_id("gpt-class"),
            name="GPT-class",
            origin=ModelOrigin.THIRD_PARTY,
            **SIMULATED,
        ),
        Model(
            id=ids.model_id("screening-lr"),
            name="Screening LR",
            origin=ModelOrigin.IN_HOUSE,
            **COMMON,
        ),
        Framework(
            id=EUAIA,
            name="EU AI Act (test fixture)",
            source_version="test fixture",
            source_url="https://example.invalid/test-fixture",
            last_verified=date(2026, 11, 5),
            **COMMON,
        ),
        Framework(
            id=ISO,
            name="ISO/IEC 42001 (test fixture)",
            source_version="test fixture",
            source_url="https://example.invalid/test-fixture",
            last_verified=date(2026, 11, 5),
            **COMMON,
        ),
        _requirement("euaia", "art4", "Art. 4"),
        _requirement("euaia", "art9", "Art. 9"),
        _requirement("euaia", "art9-2a", "Art. 9(2)(a)"),
        _requirement("euaia", "art14", "Art. 14"),
        _requirement("euaia", "art25", "Art. 25"),
        _requirement("euaia", "art50-1", "Art. 50(1)"),
        _requirement("iso42001", "A.6", "A.6"),
        _requirement("iso42001", "A.6.2.4", "A.6.2.4"),
        _requirement("iso42001", "A.8.2", "A.8.2"),
        _requirement("iso42001", "A.9", "A.9"),
        _requirement("iso42001", "A.9.3", "A.9.3"),
        _requirement("iso42001", "A.10.3", "A.10.3"),
        _requirement("iso42001", "A.7.4", "A.7.4"),
        _control("VC-001", "AI literacy", ControlKind.ORGANISATIONAL, ScopeLevel.ORGANISATION),
        _control(
            "VC-012",
            "AI interaction disclosure",
            ControlKind.TECHNICAL,
            ScopeLevel.SYSTEM,
            automatable=True,
        ),
        _control("VC-014", "Human oversight", ControlKind.ORGANISATIONAL, ScopeLevel.SYSTEM),
        _control("VC-021", "Bias testing", ControlKind.TECHNICAL, ScopeLevel.SYSTEM),
        _control(
            "VC-030",
            "Supplier data processing agreement",
            ControlKind.LEGAL_DOCUMENTARY,
            ScopeLevel.PROVIDER,
        ),
        _assessment(
            VC_AI_LITERACY,
            ORG,
            ImplementationStatus.PARTIALLY_IMPLEMENTED,
            AssuranceLevel.L1_DECLARED,
        ),
        _assessment(
            VC_DISCLOSURE, SUPPORT, ImplementationStatus.IMPLEMENTED, AssuranceLevel.L3_TESTED
        ),
        _assessment(
            VC_OVERSIGHT,
            TALENT,
            ImplementationStatus.IMPLEMENTED,
            AssuranceLevel.L4_VERIFIED,
            source=Source.SIMULATED,
            assessor=VERIFIER,
        ),
        _assessment(
            VC_BIAS_TEST, TALENT, ImplementationStatus.NOT_IMPLEMENTED, AssuranceLevel.L0_INFERRED
        ),
        _assessment(
            VC_SUPPLIER_DPA,
            BEDROCK,
            ImplementationStatus.PARTIALLY_IMPLEMENTED,
            AssuranceLevel.L2_EVIDENCED,
        ),
        _assessment(
            VC_SUPPLIER_DPA,
            OPENAI,
            ImplementationStatus.NOT_IMPLEMENTED,
            AssuranceLevel.L0_INFERRED,
        ),
        disclosure_test,
        oversight_signoff,
        talent_config,
        contract_config,
        contract_transfer_record,
        bedrock_dpa,
        _control(
            "VC-041",
            "Approved egress endpoints",
            ControlKind.TECHNICAL,
            ScopeLevel.SYSTEM,
            automatable=True,
        ),
        _assessment(
            VC_EGRESS, CONTRACT, ImplementationStatus.IMPLEMENTED, AssuranceLevel.L3_TESTED
        ),
    ]
    for node in nodes:
        repo.upsert_node(node)

    edges = [
        # Who runs, owns and is exposed to what
        make_edge(EdgeType.RUNS_ON, SUPPORT, RES_SUPPORT),
        make_edge(EdgeType.RUNS_ON, TALENT, RES_TALENT),
        make_edge(EdgeType.RUNS_ON, CONTRACT, RES_CONTRACT),
        make_edge(EdgeType.OWNS, SUPPORT_LEAD, SUPPORT),
        make_edge(EdgeType.OWNS, HR_LEAD, TALENT),
        make_edge(EdgeType.OWNS, VERIFIER, CONTRACT),
        make_edge(EdgeType.HAS_RISK, SUPPORT, RISK_SUPPORT),
        make_edge(EdgeType.HAS_RISK, TALENT, RISK_TALENT),
        make_edge(EdgeType.HAS_RISK, CONTRACT, RISK_CONTRACT),
        make_edge(EdgeType.OWNS, SUPPORT_LEAD, RISK_SUPPORT),
        make_edge(EdgeType.OWNS, HR_LEAD, RISK_TALENT),
        make_edge(EdgeType.OWNS, VERIFIER, RISK_CONTRACT),
        make_edge(EdgeType.MITIGATED_BY, RISK_SUPPORT, VC_DISCLOSURE),
        make_edge(EdgeType.MITIGATED_BY, RISK_TALENT, VC_BIAS_TEST),
        make_edge(EdgeType.MITIGATED_BY, RISK_CONTRACT, VC_SUPPLIER_DPA),
        # Changes the crawler would have detected
        make_edge(EdgeType.AFFECTS, CHG_SUPPORT, RES_SUPPORT),
        make_edge(EdgeType.AFFECTS, CHG_TALENT, RES_TALENT),
        make_edge(EdgeType.AFFECTS, CHG_CONTRACT, RES_CONTRACT),
        # Models and providers
        make_edge(EdgeType.USES_MODEL, SUPPORT, ids.model_id("bedrock-fm")),
        make_edge(EdgeType.USES_MODEL, CONTRACT, ids.model_id("gpt-class")),
        make_edge(EdgeType.USES_MODEL, TALENT, ids.model_id("screening-lr")),
        make_edge(
            EdgeType.PROVIDED_BY, ids.model_id("bedrock-fm"), BEDROCK, source=Source.SIMULATED
        ),
        make_edge(EdgeType.PROVIDED_BY, ids.model_id("gpt-class"), OPENAI, source=Source.SIMULATED),
        # Requirement hierarchy
        *(make_edge(EdgeType.PART_OF, r, EUAIA) for r in (ART4, ART9, ART14, ART25, ART50_1)),
        make_edge(EdgeType.PART_OF, ART9_2A, ART9),
        *(
            make_edge(EdgeType.PART_OF, r, ISO)
            for r in (ISO_A6, ISO_A7_4, ISO_A8_2, ISO_A9, ISO_A10_3)
        ),
        make_edge(EdgeType.PART_OF, ISO_A6_2_4, ISO_A6),
        make_edge(EdgeType.PART_OF, ISO_A9_3, ISO_A9),
        # Spokes: requirement to hub control
        _map(ART4, VC_AI_LITERACY, subset, 6, full),
        _map(ART50_1, VC_DISCLOSURE, subset, 8, full),
        _map(ART9_2A, VC_BIAS_TEST, subset, 7, full),
        _map(ART14, VC_OVERSIGHT, subset, 8, full),
        _map(ISO_A6_2_4, VC_OVERSIGHT, subset, 7, full),
        _map(ISO_A8_2, VC_DISCLOSURE, StrmType.INTERSECTS_WITH, 5, partial),
        _map(ISO_A9_3, VC_BIAS_TEST, StrmType.SUPERSET_OF, 6, partial),
        _map(ISO_A10_3, VC_SUPPLIER_DPA, subset, 7, full),
        _map(ART25, VC_SUPPLIER_DPA, StrmType.NO_RELATIONSHIP, None, None),
        _map(ISO_A7_4, VC_EGRESS, subset, 6, full),
        # What applies to whom (one edge per role)
        _applies(ART4, ORG, Role.PROVIDER, "test-org-provider"),
        _applies(ART4, ORG, Role.DEPLOYER, "test-org-deployer"),
        _applies(ART50_1, SUPPORT, Role.PROVIDER, "test-transparency"),
        _applies(ART9, TALENT, Role.PROVIDER, "test-high-risk"),
        _applies(ART9_2A, TALENT, Role.PROVIDER, "test-high-risk"),
        _applies(ART14, TALENT, Role.PROVIDER, "test-high-risk"),
        _applies(ISO_A7_4, CONTRACT, Role.ANY, "test-data-flows"),
        *(_applies(ISO_A10_3, s, Role.ANY, "test-supplier") for s in (SUPPORT, TALENT, CONTRACT)),
        # Assessments: which control, for whom
        *(
            e
            for control, scope in (
                (VC_AI_LITERACY, ORG),
                (VC_DISCLOSURE, SUPPORT),
                (VC_OVERSIGHT, TALENT),
                (VC_BIAS_TEST, TALENT),
                (VC_SUPPLIER_DPA, BEDROCK),
                (VC_SUPPLIER_DPA, OPENAI),
                (VC_EGRESS, CONTRACT),
            )
            for e in (
                make_edge(EdgeType.ASSESSES, ca(control, scope), control),
                make_edge(EdgeType.SCOPED_TO, ca(control, scope), scope),
            )
        ),
        make_edge(EdgeType.ASSESSED, VERIFIER, ca(VC_OVERSIGHT, TALENT), source=Source.SIMULATED),
        # Evidence: what it is about, and what it supports
        make_edge(EdgeType.ABOUT, disclosure_test.id, SUPPORT),
        make_edge(EdgeType.SUPPORTS, disclosure_test.id, ca(VC_DISCLOSURE, SUPPORT)),
        make_edge(EdgeType.ABOUT, oversight_signoff.id, TALENT, source=Source.SIMULATED),
        make_edge(
            EdgeType.SUPPORTS,
            oversight_signoff.id,
            ca(VC_OVERSIGHT, TALENT),
            source=Source.SIMULATED,
        ),
        make_edge(EdgeType.COLLECTED_FROM, disclosure_test.id, RES_SUPPORT),
        make_edge(EdgeType.ABOUT, talent_config.id, TALENT),
        make_edge(EdgeType.SUPPORTS, talent_config.id, ca(VC_OVERSIGHT, TALENT)),
        make_edge(EdgeType.COLLECTED_FROM, talent_config.id, RES_TALENT),
        make_edge(EdgeType.ABOUT, contract_config.id, CONTRACT),
        make_edge(EdgeType.SUPPORTS, contract_config.id, ca(VC_EGRESS, CONTRACT)),
        make_edge(EdgeType.COLLECTED_FROM, contract_config.id, RES_CONTRACT),
        make_edge(EdgeType.ABOUT, contract_transfer_record.id, CONTRACT),
        make_edge(EdgeType.SUPPORTS, contract_transfer_record.id, ca(VC_EGRESS, CONTRACT)),
        make_edge(EdgeType.ABOUT, bedrock_dpa.id, BEDROCK),
        make_edge(EdgeType.SUPPORTS, bedrock_dpa.id, ca(VC_SUPPLIER_DPA, BEDROCK)),
    ]
    for edge in edges:
        repo.upsert_edge(edge)
