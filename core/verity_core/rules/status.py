"""Whether an obligation applies at a point in time. Pure and derived from `as_of`, never
stored (D5, ADR 0019)."""

from datetime import UTC, datetime
from enum import StrEnum

from verity_core.model.edges import AppliesToEdge


class ApplicabilityStatus(StrEnum):
    IN_FORCE = "in_force"
    UPCOMING = "upcoming"
    CONDITIONAL = "conditional"


def applicability_status(edge: AppliesToEdge, as_of: datetime) -> ApplicabilityStatus:
    """Conditional if the edge has a condition. Otherwise upcoming before `in_force_from`, else
    in force. No date means in force."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if edge.condition is not None:
        return ApplicabilityStatus.CONDITIONAL
    if edge.in_force_from is not None and as_of.astimezone(UTC).date() < edge.in_force_from:
        return ApplicabilityStatus.UPCOMING
    return ApplicabilityStatus.IN_FORCE
