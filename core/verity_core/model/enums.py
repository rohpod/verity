"""Enums shared by every node and edge (docs/architecture.md section E)."""

from enum import StrEnum


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
