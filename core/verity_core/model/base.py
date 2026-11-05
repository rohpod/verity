"""Base class and the envelope carried by every node and edge."""

from datetime import UTC
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from verity_core.model.enums import NodeType, Source
from verity_core.model.ids import check_id


def _to_utc(value: AwareDatetime) -> AwareDatetime:
    return value.astimezone(UTC)


# Timezone-aware, normalised to UTC. Naive datetimes are rejected: rules and assessment
# take an explicit as_of (D5), and a naive value would make that comparison ambiguous.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]


class VerityRecord(BaseModel):
    """Immutable and strict: unknown fields are errors, so nothing (such as an email
    address, D10) can slip into a record by accident."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Envelope(VerityRecord):
    """Fields on every node and edge.

    `created_at`, `updated_at` and `version` are stamped by the repository on write, so a
    freshly built record has `version == 0` and no timestamps. `valid_from` and `valid_to`
    bound the record's existence in the graph. They are not Evidence `valid_until`, which
    says how long a piece of evidence stays fresh.
    """

    tenant: str = Field(min_length=1)
    source: Source
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None
    version: int = Field(default=0, ge=0)
    valid_from: UtcDatetime | None = None
    valid_to: UtcDatetime | None = None


class NodeBase(Envelope):
    """A graph node. Subclasses set `type`, and the ID prefix must match it."""

    id: str
    type: NodeType

    @model_validator(mode="after")
    def _id_matches_type(self) -> "NodeBase":
        check_id(self.id, self.type)
        return self
