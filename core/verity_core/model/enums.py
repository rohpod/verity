"""Enums shared by every node and edge (docs/architecture.md section E)."""

from enum import IntEnum, StrEnum


class Source(StrEnum):
    """Where a record came from. One value maps to one provenance badge (D12)."""

    DISCOVERED = "discovered"
    DECLARED = "declared"
    SEEDED = "seeded"
    SYNTHETIC = "synthetic"
    DERIVED = "derived"
    SIMULATED = "simulated"


class NodeType(StrEnum):
    ORGANISATION = "Organisation"
    DEPARTMENT = "Department"
    PERSON = "Person"
    AI_SYSTEM = "AISystem"
    CANDIDATE = "Candidate"
    AWS_RESOURCE = "AWSResource"
    MODEL = "Model"
    PROVIDER = "Provider"
    DATASET = "Dataset"
    RISK = "Risk"
    CONTROL = "Control"
    CONTROL_ASSESSMENT = "ControlAssessment"
    REQUIREMENT = "Requirement"
    FRAMEWORK = "Framework"
    EVIDENCE = "Evidence"
    POLICY = "Policy"
    DISCOVERY_RUN = "DiscoveryRun"
    CHANGE_EVENT = "ChangeEvent"


class SystemKind(StrEnum):
    GENERATIVE_AI = "generative_ai"
    CLASSICAL_ML = "classical_ml"
    EXTERNAL_AI_API = "external_ai_api"


class AiLikelihood(StrEnum):
    """How strongly the discovery signals suggest a resource is AI (architecture section D)."""

    DECLARED = "declared"
    CONFIRMED_USAGE = "confirmed_usage"
    PROBABLE = "probable"
    POSSIBLE = "possible"
    NONE = "none"


class ModelOrigin(StrEnum):
    IN_HOUSE = "in_house"
    THIRD_PARTY = "third_party"


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ControlKind(StrEnum):
    TECHNICAL = "technical"
    ORGANISATIONAL = "organisational"
    LEGAL_DOCUMENTARY = "legal_documentary"


class ScopeLevel(StrEnum):
    ORGANISATION = "organisation"
    SYSTEM = "system"
    PROVIDER = "provider"


class ImplementationStatus(StrEnum):
    IMPLEMENTED = "implemented"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    NOT_IMPLEMENTED = "not_implemented"
    NOT_ASSESSED = "not_assessed"
    NOT_APPLICABLE = "not_applicable"


class AssuranceLevel(IntEnum):
    """The assurance ladder (ADR 0005). Ordered, so `level >= L2_EVIDENCED` works."""

    L0_INFERRED = 0
    L1_DECLARED = 1
    L2_EVIDENCED = 2
    L3_TESTED = 3
    L4_VERIFIED = 4


class EvidenceKind(StrEnum):
    CONFIG_SNAPSHOT = "config_snapshot"
    AUTOMATED_TEST = "automated_test"
    USAGE_RECORD = "usage_record"
    ATTESTATION = "attestation"
    DOCUMENT_REF = "document_ref"


class RunMode(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"


class EdgeType(StrEnum):
    MEMBER_OF = "MEMBER_OF"
    PART_OF = "PART_OF"
    OWNS = "OWNS"
    DEVELOPS = "DEVELOPS"
    APPROVES_RISK_FOR = "APPROVES_RISK_FOR"
    RUNS_ON = "RUNS_ON"
    ASSUMES = "ASSUMES"
    CALLS = "CALLS"
    USES_MODEL = "USES_MODEL"
    PROVIDED_BY = "PROVIDED_BY"
    PROCESSES = "PROCESSES"
    TRAINED_ON = "TRAINED_ON"
    DERIVED_FROM = "DERIVED_FROM"
    PROMOTED_TO = "PROMOTED_TO"
    HAS_RISK = "HAS_RISK"
    MITIGATED_BY = "MITIGATED_BY"
    MAPS_TO = "MAPS_TO"
    APPLIES_TO = "APPLIES_TO"
    ASSESSES = "ASSESSES"
    SCOPED_TO = "SCOPED_TO"
    ASSESSED = "ASSESSED"
    SUPPORTS = "SUPPORTS"
    ABOUT = "ABOUT"
    COLLECTED_FROM = "COLLECTED_FROM"
    IMPLEMENTS = "IMPLEMENTS"
    OBSERVED = "OBSERVED"
    AFFECTS = "AFFECTS"


class VerifiedAgainst(StrEnum):
    """What a requirement's wording was checked against (ADR 0017). ISO entries are always
    `public_listing`, so nothing implies a check against the standard itself."""

    PRIMARY_TEXT = "primary_text"
    PUBLIC_LISTING = "public_listing"


class Direction(StrEnum):
    OUT = "out"
    IN = "in"


class Role(StrEnum):
    """Role under the EU AI Act. `any` is for requirements that are not role-based."""

    PROVIDER = "provider"
    DEPLOYER = "deployer"
    IMPORTER = "importer"
    DISTRIBUTOR = "distributor"
    ANY = "any"


class AppliesCondition(StrEnum):
    """Why an `APPLIES_TO` edge is conditional rather than in force or upcoming (ADR 0019)."""

    # Art. 111(2): a high-risk system placed on the market before Chapter III applies is in
    # scope only after a significant change in its design.
    LEGACY_SIGNIFICANT_CHANGE = "legacy_significant_change"


class Purpose(StrEnum):
    """Why a system processes a dataset. `training` means this system itself runs training;
    `TRAINED_ON` is model lineage (ADR 0012)."""

    INFERENCE = "inference"
    TRAINING = "training"
    RETRIEVAL = "retrieval"


class StrmType(StrEnum):
    """NIST IR 8477 set theory relationship types."""

    EQUAL = "equal"
    SUBSET_OF = "subset_of"
    SUPERSET_OF = "superset_of"
    INTERSECTS_WITH = "intersects_with"
    NO_RELATIONSHIP = "no_relationship"


class RationaleType(StrEnum):
    SYNTACTIC = "syntactic"
    SEMANTIC = "semantic"
    FUNCTIONAL = "functional"


class Sufficiency(StrEnum):
    FULL = "full"
    PARTIAL = "partial"


# The node type a ControlAssessment must be scoped to, for a control of each scope level.
SCOPE_NODE_TYPE: dict[ScopeLevel, NodeType] = {
    ScopeLevel.ORGANISATION: NodeType.ORGANISATION,
    ScopeLevel.SYSTEM: NodeType.AI_SYSTEM,
    ScopeLevel.PROVIDER: NodeType.PROVIDER,
}
