"""The shape of the YAML files under `content/`.

These are input models, separate from the graph's node and edge models. Every one forbids
unknown fields, so a stray key (an `excerpt` on an ISO entry, say) is an error rather than
ignored. Whether a file is *good* content is the linter's job (`lint.py`); this only checks it
can be read.
"""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from verity_core.model.enums import (
    ControlKind,
    RationaleType,
    ScopeLevel,
    StrmType,
    Sufficiency,
    VerifiedAgainst,
)

NonEmpty = Annotated[str, Field(min_length=1)]
# One part of an ID, so it can never corrupt a `#`-delimited key (see `ids.make_id`).
Slug = Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+$")]
ControlCode = Annotated[str, Field(pattern=r"^VC-\d{3}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FrameworkIn(_Strict):
    slug: Slug
    name: NonEmpty
    source_url: NonEmpty
    source_version: NonEmpty
    last_verified: date
    # ISO text is copyrighted: such a framework holds IDs and original summaries only.
    copyrighted: bool = False


class RequirementIn(_Strict):
    id: Slug
    ref: NonEmpty
    summary: NonEmpty
    parent: Slug | None = None  # another requirement of the same framework
    # Each defaults to the framework's value, for the few entries that differ.
    source_url: NonEmpty | None = None
    source_version: NonEmpty | None = None
    last_verified: date | None = None
    verified_against: VerifiedAgainst
    # Public pages that agree on this ID. ISO entries need two on different sites (ADR 0017).
    listing_sources: list[NonEmpty] = Field(default_factory=list)


class FrameworkFile(_Strict):
    framework: FrameworkIn
    requirements: list[RequirementIn]


class ControlIn(_Strict):
    code: ControlCode
    title: NonEmpty
    summary: NonEmpty
    kind: ControlKind
    automatable: bool = False
    scope_level: ScopeLevel


class ControlsFile(_Strict):
    controls: list[ControlIn]


class MappingIn(_Strict):
    """One requirement to one control. The requirement is concept A and the control is
    concept B (ADR 0017)."""

    requirement: Slug
    control: ControlCode
    strm: StrmType
    strength: int | None = None
    rationale_type: RationaleType
    rationale: NonEmpty
    sufficiency: Sufficiency | None = None


class MappingsFile(_Strict):
    framework: Slug
    mappings: list[MappingIn]


class ObligationDate(_Strict):
    """When an obligation starts to apply. Dates are data with a source (CLAUDE.md), and live
    here rather than on `Requirement` because one article can have several (ADR 0017)."""

    id: Slug
    date: date
    covers: NonEmpty
    source_url: NonEmpty
    last_verified: date


class ObligationDatesFile(_Strict):
    dates: list[ObligationDate]
