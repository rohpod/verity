"""The 27 edge types (docs/architecture.md section E, ADR 0012).

An edge is identified by `(src, type, dst, qualifier)`. The qualifier is `role` on
APPLIES_TO and `purpose` on PROCESSES, so one system can have an edge per role. Every
other edge type has no qualifier. Which node types an edge may connect is checked on
write (`validation.py`), not here, because that needs the nodes.
"""

from datetime import date
from typing import Annotated, Literal, NamedTuple

from pydantic import Field, TypeAdapter, model_validator

from verity_core.model.base import Envelope, UtcDatetime
from verity_core.model.enums import (
    EdgeType,
    Purpose,
    RationaleType,
    Role,
    StrmType,
    Sufficiency,
)
from verity_core.model.ids import node_type_of

NonEmpty = Annotated[str, Field(min_length=1)]
Interval = tuple[UtcDatetime, UtcDatetime]


class EdgeKey(NamedTuple):
    src: str
    type: EdgeType
    dst: str
    qualifier: str | None


class EdgeBase(Envelope):
    src: str
    dst: str
    type: EdgeType
    # Earlier periods when this edge existed, newest last. Reopening a closed edge moves
    # (valid_from, valid_to) here so point-in-time queries stay correct (ADR 0012).
    closed_intervals: tuple[Interval, ...] = ()

    @model_validator(mode="after")
    def _check_endpoints_and_intervals(self) -> "EdgeBase":
        node_type_of(self.src)
        node_type_of(self.dst)
        if self.src == self.dst:
            raise ValueError(f"{self.type} edge cannot connect {self.src!r} to itself")
        for start, end in self.closed_intervals:
            if end < start:
                raise ValueError("a closed interval ends before it starts")
        return self

    @property
    def qualifier(self) -> str | None:
        return None

    @property
    def key(self) -> EdgeKey:
        return EdgeKey(self.src, self.type, self.dst, self.qualifier)


class MapsToEdge(EdgeBase):
    """Requirement to Control, with an NIST IR 8477 STRM relationship."""

    type: Literal[EdgeType.MAPS_TO] = EdgeType.MAPS_TO
    strm: StrmType
    strength: int | None = Field(default=None, ge=1, le=10)
    rationale_type: RationaleType
    rationale: NonEmpty
    sufficiency: Sufficiency | None = None

    @model_validator(mode="after")
    def _no_relationship_has_no_strength_or_sufficiency(self) -> "MapsToEdge":
        # A mapping that says "no relationship" must never count towards Satisfied.
        empty = self.strength is None and self.sufficiency is None
        if self.strm is StrmType.NO_RELATIONSHIP and not empty:
            raise ValueError("no_relationship takes no strength or sufficiency")
        if self.strm is not StrmType.NO_RELATIONSHIP and (
            self.strength is None or self.sufficiency is None
        ):
            raise ValueError(f"{self.strm} needs a strength and a sufficiency")
        return self


class AppliesToEdge(EdgeBase):
    """Requirement to AISystem or Organisation. Whether it is in force or upcoming is derived
    from `as_of` (D5), never stored."""

    type: Literal[EdgeType.APPLIES_TO] = EdgeType.APPLIES_TO
    role: Role
    rule_id: NonEmpty
    reason: NonEmpty
    in_force_from: date | None = None

    @property
    def qualifier(self) -> str:
        return self.role.value


class ProcessesEdge(EdgeBase):
    type: Literal[EdgeType.PROCESSES] = EdgeType.PROCESSES
    purpose: Purpose

    @property
    def qualifier(self) -> str:
        return self.purpose.value


class PlainEdge(EdgeBase):
    """The 24 edge types with no properties of their own and no qualifier."""

    type: Literal[
        EdgeType.MEMBER_OF,
        EdgeType.PART_OF,
        EdgeType.OWNS,
        EdgeType.DEVELOPS,
        EdgeType.APPROVES_RISK_FOR,
        EdgeType.RUNS_ON,
        EdgeType.ASSUMES,
        EdgeType.CALLS,
        EdgeType.USES_MODEL,
        EdgeType.PROVIDED_BY,
        EdgeType.TRAINED_ON,
        EdgeType.DERIVED_FROM,
        EdgeType.PROMOTED_TO,
        EdgeType.HAS_RISK,
        EdgeType.MITIGATED_BY,
        EdgeType.ASSESSES,
        EdgeType.SCOPED_TO,
        EdgeType.ASSESSED,
        EdgeType.SUPPORTS,
        EdgeType.ABOUT,
        EdgeType.COLLECTED_FROM,
        EdgeType.IMPLEMENTS,
        EdgeType.OBSERVED,
        EdgeType.AFFECTS,
    ]


Edge = Annotated[
    MapsToEdge | AppliesToEdge | ProcessesEdge | PlainEdge,
    Field(discriminator="type"),
]

_EDGE_ADAPTER: TypeAdapter[Edge] = TypeAdapter(Edge)


def parse_edge(data: object) -> Edge:
    """Build the right edge class from a dict, using its `type` field."""
    return _EDGE_ADAPTER.validate_python(data)
