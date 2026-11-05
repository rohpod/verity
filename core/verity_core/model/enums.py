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
