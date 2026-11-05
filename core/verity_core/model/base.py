"""Base class and the envelope carried by every node and edge."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from verity_core.model.enums import NodeType, Source
from verity_core.model.ids import check_id


def _to_utc(value: AwareDatetime) -> AwareDatetime:
    return value.astimezone(UTC)


# Timezone-aware, normalised to UTC. Naive datetimes are rejected: rules and assessment
# take an explicit as_of (D5), and a naive value would make that comparison ambiguous.
UtcDatetime = Annotated[AwareDatetime, AfterValidator(_to_utc)]

# Tenants end up inside `#`-delimited DynamoDB keys, like IDs.
Tenant = Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+$")]


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

    tenant: Tenant
    source: Source
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None
    version: int = Field(default=0, ge=0)
    valid_from: UtcDatetime | None = None
    valid_to: UtcDatetime | None = None

    @model_validator(mode="after")
    def _validity_is_ordered(self) -> "Envelope":
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to is before valid_from")
        return self

    def is_active(self, as_of: datetime | None = None) -> bool:
        """Open now (`as_of=None`), or valid at `as_of`. The period is half-open: `[from, to)`."""
        if as_of is None:
            return self.valid_to is None
        if as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        return (self.valid_from is None or self.valid_from <= as_of) and (
            self.valid_to is None or as_of < self.valid_to
        )


class NodeBase(Envelope):
    """A graph node. Subclasses set `type`, and the ID prefix must match it."""

    id: str
    type: NodeType

    @model_validator(mode="after")
    def _id_matches_type(self) -> "NodeBase":
        check_id(self.id, self.type)
        return self
