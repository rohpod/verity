"""The 18 node types (docs/architecture.md section E).

Fields are the minimum that sections C, E, F and G name, plus what the traversals need.
Later milestones add fields when content or rules need them. Every model forbids unknown
fields, so for example a `Person` can never carry an email address (D10).
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, field_validator, model_validator

from verity_core.model.base import NodeBase, UtcDatetime
from verity_core.model.enums import (
    AiLikelihood,
    AssuranceLevel,
    ControlKind,
    DataClassification,
    ImplementationStatus,
    ModelOrigin,
    NodeType,
    Role,
    RunMode,
    ScopeLevel,
    SystemKind,
    VerifiedAgainst,
)
from verity_core.model.evidence import Evidence
from verity_core.model.ids import check_id

NonEmpty = Annotated[str, Field(min_length=1)]
EnvVarName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")]
UseDomain = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]


class Organisation(NodeBase):
    type: Literal[NodeType.ORGANISATION] = NodeType.ORGANISATION
    name: NonEmpty


class Department(NodeBase):
    type: Literal[NodeType.DEPARTMENT] = NodeType.DEPARTMENT
    name: NonEmpty


class Person(NodeBase):
    """Accountability only, never activity tracking. Always a fictional person."""

    type: Literal[NodeType.PERSON] = NodeType.PERSON
    name: NonEmpty
    job_title: str | None = None


class AISystem(NodeBase):
    type: Literal[NodeType.AI_SYSTEM] = NodeType.AI_SYSTEM
    name: NonEmpty
    purpose: NonEmpty
    kind: SystemKind
    # Facts the applicability rules read (ADR 0017). Unknown unless stated, and never a risk
    # tier: that is an output of M5 and a human decision (ADR 0008).
    roles: list[Role] = Field(default_factory=list)
    use_domains: list[UseDomain] = Field(default_factory=list)
    interacts_with_people: bool | None = None
    generates_synthetic_content: bool | None = None
    first_placed_on_market: date | None = None
    # The last significant design change, for Art. 111(2) (ADR 0019). Unknown or never: None.
    significant_change_on: date | None = None

    @field_validator("roles")
    @classmethod
    def _roles_are_specific(cls, roles: list[Role]) -> list[Role]:
        if Role.ANY in roles:
            raise ValueError("`any` is for requirements; a system has a specific role")
        return roles


class Candidate(NodeBase):
    """A resource that scored probable or possible but is not yet in the registry."""

    type: Literal[NodeType.CANDIDATE] = NodeType.CANDIDATE
    name: NonEmpty
    ai_likelihood: AiLikelihood
    signals: list[str] = Field(default_factory=list)  # the signals that fired, to explain why


class AWSResource(NodeBase):
    type: Literal[NodeType.AWS_RESOURCE] = NodeType.AWS_RESOURCE
    resource_type: NonEmpty
    region: NonEmpty
    name: NonEmpty
    tags: dict[str, str] = Field(default_factory=dict)
    # Names only: the collector discards values on receipt (D1). The pattern is a second line
    # of defence that refuses `NAME=value`; it cannot recognise a bare value as one.
    env_var_names: list[EnvVarName] = Field(default_factory=list)
    config_hash: str | None = None  # compared between runs to produce ChangeEvents


class Model(NodeBase):
    type: Literal[NodeType.MODEL] = NodeType.MODEL
    name: NonEmpty
    origin: ModelOrigin


class Provider(NodeBase):
    type: Literal[NodeType.PROVIDER] = NodeType.PROVIDER
    name: NonEmpty
    simulated: bool  # true for mock-bedrock and mock-openai, so mocks are explicit in the data


class Dataset(NodeBase):
    type: Literal[NodeType.DATASET] = NodeType.DATASET
    name: NonEmpty
    classification: DataClassification
    personal_data: bool


class Risk(NodeBase):
    type: Literal[NodeType.RISK] = NodeType.RISK
    title: NonEmpty
    description: NonEmpty


class Control(NodeBase):
    """A reusable definition in the Verity Control Library. Status lives on ControlAssessment."""

    type: Literal[NodeType.CONTROL] = NodeType.CONTROL
    title: NonEmpty
    summary: NonEmpty
    kind: ControlKind
    automatable: bool
    scope_level: ScopeLevel

    @model_validator(mode="after")
    def _only_technical_controls_are_automatable(self) -> "Control":
        if self.automatable and self.kind is not ControlKind.TECHNICAL:
            raise ValueError(f"a {self.kind} control cannot be automatable (ADR 0012)")
        return self


class ControlAssessment(NodeBase):
    """Control x scope. Holds status and assurance, never the Control itself (ADR 0005)."""

    type: Literal[NodeType.CONTROL_ASSESSMENT] = NodeType.CONTROL_ASSESSMENT
    status: ImplementationStatus
    assurance_level: AssuranceLevel
    method: str | None = None
    assessed_at: UtcDatetime | None = None
    assessor: str | None = None  # person ID; the ASSESSED edge carries the same link

    @model_validator(mode="after")
    def _l4_needs_a_named_person(self) -> "ControlAssessment":
        if self.assessor is not None:
            check_id(self.assessor, NodeType.PERSON)
        if self.assurance_level is AssuranceLevel.L4_VERIFIED and self.assessor is None:
            raise ValueError("L4 Verified needs a named assessor")
        return self


class Requirement(NodeBase):
    """One clause or article. ISO entries hold the ID plus an original summary only."""

    type: Literal[NodeType.REQUIREMENT] = NodeType.REQUIREMENT
    ref: NonEmpty
    summary: NonEmpty
    source_url: NonEmpty
    # The legal text's version, for example "2024/1689 as amended by 2026/1744". Not `version`,
    # which is the record revision counter on every node.
    source_version: NonEmpty
    last_verified: date
    verified_against: VerifiedAgainst


class Framework(NodeBase):
    type: Literal[NodeType.FRAMEWORK] = NodeType.FRAMEWORK
    name: NonEmpty
    source_version: NonEmpty
    source_url: NonEmpty
    last_verified: date


class Policy(NodeBase):
    type: Literal[NodeType.POLICY] = NodeType.POLICY
    title: NonEmpty
    summary: NonEmpty


class DiscoveryRun(NodeBase):
    type: Literal[NodeType.DISCOVERY_RUN] = NodeType.DISCOVERY_RUN
    mode: RunMode
    started_at: UtcDatetime
    finished_at: UtcDatetime | None = None
    crawler_version: NonEmpty


class ChangeEvent(NodeBase):
    type: Literal[NodeType.CHANGE_EVENT] = NodeType.CHANGE_EVENT
    # Evidence collected before this instant is made stale by the change (ADR 0012).
    detected_at: UtcDatetime
    previous_config_hash: str | None = None
    new_config_hash: str | None = None


Node = Annotated[
    Organisation
    | Department
    | Person
    | AISystem
    | Candidate
    | AWSResource
    | Model
    | Provider
    | Dataset
    | Risk
    | Control
    | ControlAssessment
    | Requirement
    | Framework
    | Evidence
    | Policy
    | DiscoveryRun
    | ChangeEvent,
    Field(discriminator="type"),
]

_NODE_ADAPTER: TypeAdapter[Node] = TypeAdapter(Node)


def parse_node(data: object) -> Node:
    """Build the right node class from a dict, using its `type` field."""
    return _NODE_ADAPTER.validate_python(data)
