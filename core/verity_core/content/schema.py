"""The shape of the YAML files under `content/`.

These are input models, separate from the graph's node and edge models. Every one forbids
unknown fields, so a stray key (an `excerpt` on an ISO entry, say) is an error rather than
ignored. Whether a file is *good* content is the linter's job (`lint.py`); this only checks it
can be read.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from verity_core.model.enums import (
    ControlKind,
    DataClassification,
    ImplementationStatus,
    ModelOrigin,
    Purpose,
    RationaleType,
    Role,
    ScopeLevel,
    Source,
    StrmType,
    Sufficiency,
    SystemKind,
    VerifiedAgainst,
)

NonEmpty = Annotated[str, Field(min_length=1)]
# One part of an ID, so it can never corrupt a `#`-delimited key (see `ids.make_id`).
Slug = Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+$")]
ControlCode = Annotated[str, Field(pattern=r"^VC-\d{3}$")]
UseDomain = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FrameworkIn(_Strict):
    slug: Slug
    name: NonEmpty
    source_url: NonEmpty
    source_version: NonEmpty
    last_verified: date
    binding: bool  # law that binds the organisation, not a standard it adopted (ADR 0020)
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


# --- applicability rules (`rules/applicability.yaml`, ADR 0019) ----------------------------

RequirementRef = Annotated[str, Field(pattern=r"^req:[A-Za-z0-9._-]+:[A-Za-z0-9._-]+$")]
SystemFact = Literal["interacts_with_people", "generates_synthetic_content"]


class ApplicabilityRule(_Strict):
    """Which requirements apply to whom, and from when. The rules are our reading of the law,
    not legal advice, so the owner reads this file (ADR 0019).

    Give `requirements` (named) or `leaves_of` (every leaf requirement of those frameworks).
    """

    id: Slug
    requirements: list[RequirementRef] = Field(default_factory=list)
    leaves_of: list[Slug] = Field(default_factory=list)
    target: Literal["organisation", "system"]
    # `held` is for the organisation: one edge for each of provider and deployer that any
    # system holds. Otherwise the edge has this role, and a system target must hold it.
    role: Role | Literal["held"]
    reads: list[SystemFact] = Field(default_factory=list)  # facts that must be true
    high_risk: bool = False  # the system must be high-risk, or a candidate
    date: Slug | None = None  # an obligation date ID
    # Used instead of `date` when the system was first placed on the market before it
    legacy_date: Slug | None = None
    art_111_2: bool = False  # Art. 111(2) keeps a system already on the market out of scope

    @model_validator(mode="after")
    def _consistent(self):
        if bool(self.requirements) == bool(self.leaves_of):
            raise ValueError("give either requirements or leaves_of")
        if self.role == "held" and self.target != "organisation":
            raise ValueError("role held is for an organisation target")
        if self.target == "organisation" and (self.reads or self.high_risk):
            raise ValueError("reads and high_risk are facts about a system")
        if (self.legacy_date or self.art_111_2) and self.date is None:
            raise ValueError("legacy_date and art_111_2 need a date")
        if self.art_111_2 and not self.high_risk:
            raise ValueError("art_111_2 is for high-risk rules")
        return self


class ApplicabilityFile(_Strict):
    # Annex III domains, as `use_domains` values, with where each is listed.
    annex_iii_domains: dict[UseDomain, NonEmpty]
    rules: list[ApplicabilityRule]


# --- the fictional organisation and its AI estate (`org/*.yaml`) ----------------------------

# The only provenance an organisation file may claim. `discovered` and `derived` come from the
# crawler and the engine, and `seeded` is for the library (frameworks, controls, mappings).
OrgSource = Literal[Source.DECLARED, Source.SYNTHETIC, Source.SIMULATED]


class _Item(_Strict):
    """Anything with its own provenance. The file's `source` applies unless the item has one."""

    source: OrgSource | None = None


class OrganisationIn(_Item):
    slug: Slug
    name: NonEmpty


class DepartmentIn(_Item):
    slug: Slug
    name: NonEmpty


class PersonIn(_Item):
    slug: Slug
    name: NonEmpty
    job_title: NonEmpty
    department: Slug


class ProviderIn(_Item):
    slug: Slug
    name: NonEmpty
    simulated: bool = False


class ModelIn(_Item):
    slug: Slug
    name: NonEmpty
    origin: ModelOrigin
    provider: Slug | None = None  # a third-party model's provider
    trained_on: list[Slug] = Field(default_factory=list)


class DatasetIn(_Item):
    slug: Slug
    name: NonEmpty
    classification: DataClassification
    personal_data: bool


class PolicyIn(_Item):
    slug: Slug
    title: NonEmpty
    summary: NonEmpty
    implements: list[ControlCode] = Field(default_factory=list)


class RiskIn(_Item):
    slug: Slug
    title: NonEmpty
    description: NonEmpty
    owner: Slug | None = None
    mitigated_by: list[ControlCode] = Field(default_factory=list)


class DatasetUseIn(_Strict):
    dataset: Slug
    purpose: Purpose


class SystemIn(_Item):
    slug: Slug
    name: NonEmpty
    purpose: NonEmpty
    kind: SystemKind
    owner: Slug | None = None  # a system with no owner is a deliberate gap in the demo data
    developers: list[Slug] = Field(default_factory=list)
    risk_approver: Slug | None = None
    models: list[Slug] = Field(default_factory=list)
    datasets: list[DatasetUseIn] = Field(default_factory=list)
    risks: list[Slug] = Field(default_factory=list)
    # Facts for the applicability rules (ADR 0017). Left out means unknown.
    roles: list[Role] = Field(default_factory=list)
    use_domains: list[UseDomain] = Field(default_factory=list)
    interacts_with_people: bool | None = None
    generates_synthetic_content: bool | None = None
    first_placed_on_market: date | None = None
    significant_change_on: date | None = None


class OrgFile(_Strict):
    """One file may hold any part of the estate. References between records can cross files."""

    source: OrgSource = Source.SYNTHETIC
    organisation: OrganisationIn | None = None
    departments: list[DepartmentIn] = Field(default_factory=list)
    people: list[PersonIn] = Field(default_factory=list)
    providers: list[ProviderIn] = Field(default_factory=list)
    models: list[ModelIn] = Field(default_factory=list)
    datasets: list[DatasetIn] = Field(default_factory=list)
    policies: list[PolicyIn] = Field(default_factory=list)
    risks: list[RiskIn] = Field(default_factory=list)
    systems: list[SystemIn] = Field(default_factory=list)


# --- human decisions (`decisions/*.yaml`, ADR 0008 and 0019) -------------------------------
# One decision per file, so the approving pull request names exactly what it approves.

PersonRef = Annotated[str, Field(pattern=r"^person:[A-Za-z0-9._-]+$")]
# Only what a person can decide. `not_assessed` and `not_applicable` are the engine's words.
DecidedStatus = Literal[
    ImplementationStatus.IMPLEMENTED,
    ImplementationStatus.PARTIALLY_IMPLEMENTED,
    ImplementationStatus.NOT_IMPLEMENTED,
]


class _Decision(_Strict):
    id: Slug
    decided_on: date
    by: PersonRef
    valid_until: date
    statement: NonEmpty
    # A demo sign-off by a fictional person. The statement must say "simulated sign-off" (D11).
    simulated: bool = False
    # IDs of earlier decisions this one replaces. A seeded decision is never edited (ADR 0020).
    supersedes: list[Slug] = Field(default_factory=list)

    @model_validator(mode="after")
    def _expires_after_it_is_made(self):
        if self.valid_until <= self.decided_on:
            raise ValueError("valid_until must be after decided_on")
        return self


class RiskTierDecision(_Decision):
    """Confirms or rejects a high-risk candidate (ADR 0019)."""

    kind: Literal["risk_tier"]
    system: NonEmpty  # an AISystem ID
    tier: Literal["high_risk", "not_high_risk"]
    basis: Literal["annex_iii", "not_listed", "art6_3"]
    condition: Literal["a", "b", "c", "d"] | None = None  # the Art. 6(3) condition relied on
    profiling: bool | None = None

    @model_validator(mode="after")
    def _art6_3_never_covers_profiling(self):
        if self.basis != "art6_3":
            if self.condition is not None or self.profiling is not None:
                raise ValueError("condition and profiling belong to basis art6_3 only")
        elif self.profiling:
            raise ValueError("Art. 6(3) never applies to profiling: that is always high-risk")
        elif self.condition is None or self.profiling is None:
            raise ValueError("basis art6_3 needs a condition (a to d) and profiling: false")
        return self


class RevocationDecision(_Decision):
    """Withdraws earlier decisions without replacing them (ADR 0020). It is not an assessment:
    it names no control."""

    kind: Literal["revocation"]
    subject: NonEmpty  # the organisation, system or provider the revoked decisions are about

    @model_validator(mode="after")
    def _names_what_it_revokes(self):
        if not self.supersedes:
            raise ValueError("a revocation must name the decisions it supersedes")
        return self


class _ControlDecision(_Decision):
    control: ControlCode
    scope: NonEmpty  # the ID of the organisation, system or provider the control is assessed for


class AttestationDecision(_ControlDecision):
    kind: Literal["attestation"]
    status: DecidedStatus


class VerificationDecision(_ControlDecision):
    kind: Literal["verification"]
    status: DecidedStatus


class DocumentDecision(_ControlDecision):
    kind: Literal["document"]
    path: NonEmpty  # a file under evidence/


DecisionIn = (
    RiskTierDecision
    | AttestationDecision
    | VerificationDecision
    | DocumentDecision
    | RevocationDecision
)


class DecisionFile(RootModel[DecisionIn]):
    root: DecisionIn = Field(discriminator="kind")
