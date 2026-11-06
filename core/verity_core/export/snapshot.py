"""The snapshot models, built from the public field lists (ADR 0029, decisions 3 and 11).

Each node and edge model is a copy of its source model restricted to the fields `fields.py`
publishes, so a field that is not listed cannot appear in the file. Evidence gains `redacted`,
which says the hash covers the published content and not the stored original (decision 6).

The schema is generated in serialisation mode, because every field is always written: a reader
must not have to guess what a missing `redacted` means.
"""

import operator
from functools import reduce
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from verity_core.assess.freshness import Freshness
from verity_core.assess.requirements import RequirementState
from verity_core.export.fields import (
    PUBLIC_EDGE_FIELDS,
    PUBLIC_NODE_FIELDS,
    public_fields,
    unclassified,
)
from verity_core.graph.traversals import Resolution
from verity_core.model.base import UtcDatetime, VerityRecord
from verity_core.model.enums import (
    AssuranceLevel,
    ImplementationStatus,
    Role,
    Source,
    StrmType,
    Sufficiency,
)
from verity_core.model.nodes import Evidence
from verity_core.rules.finding import Severity
from verity_core.rules.status import ApplicabilityStatus

SCHEMA_VERSION = 1
DataSource = Literal["live", "fixture"]


class SnapshotRecord(VerityRecord):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


def _restricted(model: type[BaseModel]) -> type[SnapshotRecord]:
    """A frozen, strict copy of `model` with only its public fields. Validators are not carried
    over: the values were validated when the graph was built, and the snapshot only carries them.
    A model with a field that is neither public nor withheld is refused."""
    problems = unclassified(model)
    if any(problems.values()):
        raise ValueError(f"{model.__name__} has unclassified fields: {problems}")
    declared: dict[str, Any] = {
        name: (model.model_fields[name].annotation, model.model_fields[name])
        for name in public_fields(model)
    }
    if model is Evidence:
        declared["redacted"] = (bool, Field(default=False))
    return create_model(f"Snapshot{model.__name__}", __base__=SnapshotRecord, **declared)


NODE_MODELS: dict[type[BaseModel], type[SnapshotRecord]] = {
    model: _restricted(model) for model in PUBLIC_NODE_FIELDS
}
EDGE_MODELS: dict[type[BaseModel], type[SnapshotRecord]] = {
    model: _restricted(model) for model in PUBLIC_EDGE_FIELDS
}

SnapshotNode = Annotated[reduce(operator.or_, NODE_MODELS.values()), Field(discriminator="type")]
SnapshotEdge = Annotated[reduce(operator.or_, EDGE_MODELS.values()), Field(discriminator="type")]


# --- what is derived, not stored (ADR 0029, decisions 2, 10 and 11) -------------------------
#
# Every row says `derived`: it was computed by the one assessment run that also decided the
# findings, not read from a stored record. Whether a result rests on a simulated sign-off is
# a separate flag, so a demo result never looks like a real one.


class DerivedRow(SnapshotRecord):
    source: Literal[Source.DERIVED] = Source.DERIVED


class SnapshotFinding(DerivedRow):
    code: str
    severity: Severity
    subject: str
    message: str
    control_id: str | None  # set when the finding is about one control result
    simulated: bool  # that result rests on a simulated sign-off


class SnapshotTarget(SnapshotRecord):
    control_id: str
    scope_id: str | None
    resolution: Resolution


class SnapshotRequirementStatus(DerivedRow):
    requirement_id: str
    system_id: str
    state: RequirementState
    reason: str | None
    targets: list[SnapshotTarget]
    applicability: ApplicabilityStatus | None
    simulated: bool


class SnapshotControlResult(DerivedRow):
    control_id: str
    scope_id: str
    status: ImplementationStatus
    level: AssuranceLevel
    method: str
    assessor: str | None
    simulated: bool
    evidence_id: str | None
    freshness: Freshness | None


class SnapshotObligation(DerivedRow):
    """One row of `obligations_for(system)`. The mapping itself is the MAPS_TO edge."""

    system_id: str
    requirement_id: str
    role: Role
    applies_to: str
    control_id: str | None
    strm: StrmType | None
    strength: int | None
    sufficiency: Sufficiency | None
    resolution: Resolution
    provider_id: str | None
    assessment_id: str | None
    evidence_ids: list[str]


class SnapshotSystemImpact(SnapshotRecord):
    system_id: str
    model_ids: list[str]
    owner_ids: list[str]
    risk_ids: list[str]
    requirement_ids: list[str]


class SnapshotProviderImpact(DerivedRow):
    provider_id: str
    assessment_ids: list[str]
    systems: list[SnapshotSystemImpact]


class SnapshotCrosswalkLink(SnapshotRecord):
    via_control_id: str
    target_requirement_id: str
    strength: int  # the weaker of the two mappings
    from_strm: StrmType
    to_strm: StrmType


class SnapshotCrosswalk(DerivedRow):
    """Requirement R of one framework related to requirements of another through a hub control.
    A pair of frameworks has a row for each requirement that reaches the other."""

    from_framework: str
    to_framework: str
    requirement_id: str
    links: list[SnapshotCrosswalkLink]


class SnapshotRedaction(SnapshotRecord):
    """What redaction did, as counts. Never a value."""

    steps: list[str]
    own_account_replaced: bool
    external_accounts: int
    content_keys_withheld: int
    tags_withheld: int
    evidence_rebuilt: int
    evidence_unchanged: int


class SnapshotHeader(SnapshotRecord):
    schema_version: Literal[1] = SCHEMA_VERSION
    as_of: UtcDatetime
    data_source: DataSource  # `live` is the account; `fixture` is the recorded, simulated one
    redaction: SnapshotRedaction
    simulated_components: list[str]  # everything in the file that is not real


class Snapshot(SnapshotRecord):
    """What `verity export` writes. Everything in it is a public field of the graph, or derived
    from the graph by the one assessment run named by `header.as_of`."""

    header: SnapshotHeader
    nodes: list[SnapshotNode]
    edges: list[SnapshotEdge]
    findings: list[SnapshotFinding]
    requirement_statuses: list[SnapshotRequirementStatus]
    control_results: list[SnapshotControlResult]
    obligations: list[SnapshotObligation]
    provider_impact: list[SnapshotProviderImpact]
    crosswalk: list[SnapshotCrosswalk]
