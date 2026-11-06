"""A finding: something a person should look at. Derived on read and never stored (ADR 0019)."""

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    subject: str  # the node ID the finding is about
    message: str
    control_id: str | None = None  # set when the finding is about one control result
