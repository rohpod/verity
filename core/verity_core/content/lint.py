"""The content linter: M4's gate on what may be seeded.

It checks form, not judgement. It can tell that a rationale exists and is not a one-liner, but
not that the mapping is right, so the owner still reads the mappings (ADR 0017). Like
`graph/integrity.py` it returns every issue found, and an empty list means the content passes.
"""

import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urlparse

from verity_core.content.loader import Content
from verity_core.model import ids
from verity_core.model.edges import MapsToEdge
from verity_core.model.enums import (
    SCOPE_NODE_TYPE,
    EdgeType,
    RationaleType,
    Source,
    StrmType,
    Sufficiency,
    VerifiedAgainst,
)
from verity_core.model.nodes import Control, Model, Organisation, Person, Provider

EU_FRAMEWORK = "euaia"
EU_SOURCE_VERSION = "2024/1689 as amended by 2026/1744"
ISO_SUMMARY_LIMIT = 200
MIN_RATIONALE_LENGTH = 40
MIN_EQUAL_STRENGTH = 9
MIN_LISTING_SITES = 2
MAX_UNREAD_STRENGTH = 5  # a mapping judged from a public title alone (ADR 0018)

_PLACEHOLDERS = ("example.invalid", "test fixture")
_QUOTES = ('"', "“", "”")
_SHALL = re.compile(r"\bshall\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(?:19|20)\d\d\b")
_ACCOUNT_ID = re.compile(r"(?<!\d)\d{12}(?!\d)")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")  # a digest is not text, and can hold 12 digits by chance
# Real AI vendors and products. Only a simulated provider or model may carry such a name, and
# then only with its provenance saying so (CLAUDE.md, honesty rules). A small list, not a
# complete one: it catches the likely slips, and the owner reads the estate files.
_REAL_VENDORS = re.compile(
    r"\b(openai|gpt|chatgpt|anthropic|claude|google|gemini|deepmind|microsoft|azure|copilot|"
    r"amazon|aws|bedrock|titan|nova|meta|llama|mistral|cohere|nvidia|ibm|watson|"
    r"huggingface|stability)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LintIssue:
    code: str
    subject: str
    message: str


@dataclass(frozen=True)
class LintLimits:
    """How many hub controls the library should hold (architecture section F)."""

    min_controls: int = 25
    max_controls: int = 35


def lint(content: Content, limits: LintLimits = LintLimits()) -> list[LintIssue]:  # noqa: B008
    """Every issue found, ordered by subject then code."""
    issues = [
        *_sources(content),
        *_eu_wording(content),
        *_iso_entries(content),
        *_mappings(content),
        *_coverage(content, limits),
        *_estate(content),
        *_decisions(content),
        *_rules(content),
        *_honesty(content),
    ]
    return sorted(issues, key=lambda i: (i.subject, i.code))


def _framework_of(requirement_id: str) -> str:
    return requirement_id.split(":")[1]


def _sources(content: Content) -> Iterator[LintIssue]:
    cited = [
        *((f.id, f.source_url, f.source_version) for f in content.frameworks),
        *((r.id, r.source_url, r.source_version) for r in content.requirements),
        *((f"date:{d.id}", d.source_url, "") for d in content.dates),
    ]
    for subject, url, version in cited:
        if any(p in f"{url} {version}".lower() for p in _PLACEHOLDERS):
            yield LintIssue("placeholder_source", subject, "source is a placeholder")
        if not url.startswith("https://"):
            yield LintIssue("source_url_not_https", subject, f"{url!r} is not an https URL")


def _eu_wording(content: Content) -> Iterator[LintIssue]:
    for fw in content.frameworks:
        if fw.id.split(":")[1] == EU_FRAMEWORK and fw.source_version != EU_SOURCE_VERSION:
            yield LintIssue("eu_source_version", fw.id, f"must say {EU_SOURCE_VERSION!r}")
    for req in content.requirements:
        if _framework_of(req.id) != EU_FRAMEWORK:
            continue
        if req.source_version != EU_SOURCE_VERSION:
            yield LintIssue("eu_source_version", req.id, f"must say {EU_SOURCE_VERSION!r}")
        if _YEAR.search(req.summary):
            yield LintIssue("date_in_summary", req.id, "dates belong in obligation_dates.yaml")


def _iso_entries(content: Content) -> Iterator[LintIssue]:
    for req in content.requirements:
        if _framework_of(req.id) not in content.copyrighted:
            continue
        if len(req.summary) > ISO_SUMMARY_LIMIT:
            yield LintIssue("iso_summary_too_long", req.id, f"over {ISO_SUMMARY_LIMIT} characters")
        if any(q in req.summary for q in _QUOTES):
            yield LintIssue("iso_quoted_text", req.id, "a summary must not quote the standard")
        if _SHALL.search(req.summary):
            yield LintIssue("iso_normative_wording", req.id, "'shall' suggests copied wording")
        if req.verified_against is not VerifiedAgainst.PUBLIC_LISTING:
            yield LintIssue("iso_not_public_listing", req.id, "ISO IDs are public_listing")
        sites = {urlparse(u).hostname for u in content.listing_sources.get(req.id, ())}
        if len(sites - {None}) < MIN_LISTING_SITES:
            yield LintIssue(
                "iso_listing_sources",
                req.id,
                f"needs public pages on {MIN_LISTING_SITES} different sites that agree on the ID",
            )


def _mappings(content: Content) -> Iterator[LintIssue]:
    mappings = [e for e in content.edges if isinstance(e, MapsToEdge)]
    full_per_requirement = Counter(m.src for m in mappings if m.sufficiency is Sufficiency.FULL)
    unread = {
        r.id for r in content.requirements if r.verified_against is VerifiedAgainst.PUBLIC_LISTING
    }
    for m in mappings:
        subject = f"{m.src}->{m.dst}"
        if m.src in unread and not _claims_only_what_a_title_shows(m):
            yield LintIssue(
                "unread_mapping_overclaims",
                subject,
                "without the text, use intersects_with, partial, strength "
                f"{MAX_UNREAD_STRENGTH} or less (ADR 0018)",
            )
        if m.rationale_type is RationaleType.SYNTACTIC:
            yield LintIssue("syntactic_rationale", subject, "the hub has no wording to compare")
        if len(m.rationale.strip()) < MIN_RATIONALE_LENGTH:
            yield LintIssue(
                "rationale_too_short", subject, f"under {MIN_RATIONALE_LENGTH} characters"
            )
        if m.strm is StrmType.EQUAL and (m.strength or 0) < MIN_EQUAL_STRENGTH:
            yield LintIssue(
                "equal_strength_low", subject, f"equal needs a strength of {MIN_EQUAL_STRENGTH}+"
            )
        if m.strm in (StrmType.EQUAL, StrmType.SUBSET_OF) and m.sufficiency is Sufficiency.PARTIAL:
            yield LintIssue("sufficiency_must_be_full", subject, f"{m.strm} covers the whole")
        if (
            m.strm in (StrmType.SUPERSET_OF, StrmType.INTERSECTS_WITH)
            and m.sufficiency is Sufficiency.FULL
            and full_per_requirement[m.src] < 2
        ):
            yield LintIssue(
                "full_needs_cover",
                subject,
                f"{m.strm} is full only alongside another full mapping",
            )


def _claims_only_what_a_title_shows(m: MapsToEdge) -> bool:
    if m.strm is StrmType.NO_RELATIONSHIP:
        return False  # "no overlap" is as much a claim about the text as "subset of"
    return (
        m.strm is StrmType.INTERSECTS_WITH
        and m.sufficiency is Sufficiency.PARTIAL
        and (m.strength or 0) <= MAX_UNREAD_STRENGTH
    )


def _coverage(content: Content, limits: LintLimits) -> Iterator[LintIssue]:
    mappings = [e for e in content.edges if isinstance(e, MapsToEdge)]
    parents = {e.dst for e in content.edges if e.type is EdgeType.PART_OF}
    reviewed = {m.src for m in mappings}  # `no_relationship` counts: it was looked at
    for req in content.requirements:
        if req.id not in parents and req.id not in reviewed:
            yield LintIssue("unmapped_requirement", req.id, "no mapping, not even a negative one")
    used = {m.dst for m in mappings if m.strm is not StrmType.NO_RELATIONSHIP}
    for control in content.controls:
        if control.id not in used:
            yield LintIssue("unmapped_control", control.id, "no requirement maps to it")
    count = len(content.controls)
    if not limits.min_controls <= count <= limits.max_controls:
        yield LintIssue(
            "control_count",
            "controls",
            f"{count} controls; expected {limits.min_controls} to {limits.max_controls}",
        )


def _estate(content: Content) -> Iterator[LintIssue]:
    """The demo organisation must not pass real vendors off as fictional ones, and a simulated
    component must say so in its name and in its provenance."""
    if content.estate and not any(isinstance(n, Organisation) for n in content.estate):
        yield LintIssue("no_organisation", "org", "the estate has no organisation (ADR 0012)")
    simulated_providers = set()
    for node in content.estate:
        if isinstance(node, Provider):
            if node.simulated:
                simulated_providers.add(node.id)
                if "simulated" not in node.name.lower():
                    yield LintIssue("simulated_not_labelled", node.id, "name must say 'simulated'")
            if node.simulated != (node.source is Source.SIMULATED):
                yield LintIssue(
                    "simulated_source_mismatch", node.id, "`simulated` and source disagree"
                )
        real_vendor = (
            isinstance(node, Provider | Model)
            and node.source is not Source.SIMULATED
            and _REAL_VENDORS.search(node.name)
        )
        if real_vendor:
            yield LintIssue("real_vendor_name", node.id, f"{node.name!r} names a real vendor")
    for edge in content.edges:
        if edge.type is EdgeType.PROVIDED_BY and edge.dst in simulated_providers:
            model = next(n for n in content.estate if n.id == edge.src)
            if model.source is not Source.SIMULATED:
                yield LintIssue(
                    "model_source_mismatch", model.id, "a simulated provider's model is simulated"
                )


def _decisions(content: Content) -> Iterator[LintIssue]:
    """A decision must name a real person, a real control and a scope of the right level, and a
    demo sign-off must say it is simulated (D11)."""
    estate = {n.id for n in content.estate}
    people = {n.id for n in content.estate if isinstance(n, Person)}
    controls = {c.id: c for c in content.controls if isinstance(c, Control)}
    for ev in content.decisions:
        subject = f"{ev.content['decision_id']}"
        if ev.collector not in people:
            yield LintIssue("decision_unknown_person", subject, f"{ev.collector!r} is not a person")
        if ev.subject not in estate:
            yield LintIssue("decision_unknown_scope", subject, f"{ev.subject!r} does not exist")
        if "control" in ev.content:
            control = controls.get(ev.content["control"])
            if control is None:
                yield LintIssue("decision_unknown_control", subject, "no such control")
            elif ids.node_type_of(ev.subject) is not SCOPE_NODE_TYPE[control.scope_level]:
                yield LintIssue(
                    "decision_scope_mismatch",
                    subject,
                    f"{control.id} is assessed at {control.scope_level} level",
                )
        if ev.source is Source.SIMULATED and "simulated sign-off" not in (
            ev.content["statement"].lower()
        ):
            yield LintIssue(
                "simulated_not_labelled", subject, "statement must say 'simulated sign-off'"
            )


def _rules(content: Content) -> Iterator[LintIssue]:
    """A rule may only name requirements, frameworks and dates that exist."""
    if content.rules is None:
        return
    requirements = {r.id for r in content.requirements}
    frameworks = {f.id for f in content.frameworks}
    dates = {d.id for d in content.dates}
    for rule in content.rules.rules:
        subject = f"rule:{rule.id}"
        for req in rule.requirements:
            if req not in requirements:
                yield LintIssue("rule_unknown_requirement", subject, f"{req!r} does not exist")
        for slug in rule.leaves_of:
            if ids.framework_id(slug) not in frameworks:
                yield LintIssue("rule_unknown_framework", subject, f"{slug!r} does not exist")
        for date_id in (rule.date, rule.legacy_date):
            if date_id is not None and date_id not in dates:
                yield LintIssue("rule_unknown_date", subject, f"{date_id!r} does not exist")


def _strings(content: Content) -> Iterator[tuple[str, str]]:
    """Every piece of free text in the content, with the record it belongs to."""

    def walk(subject: str, value: object) -> Iterator[tuple[str, str]]:
        if isinstance(value, str):
            if not _SHA256.fullmatch(value):
                yield subject, value
        elif isinstance(value, dict):
            for item in value.values():
                yield from walk(subject, item)
        elif isinstance(value, list | tuple):
            for item in value:
                yield from walk(subject, item)

    for node in content.nodes():
        yield from walk(node.id, node.model_dump(mode="json"))
    for edge in content.edges:
        if isinstance(edge, MapsToEdge):
            yield f"{edge.src}->{edge.dst}", edge.rationale
    for d in content.dates:
        yield from walk(f"date:{d.id}", d.model_dump(mode="json"))


def _honesty(content: Content) -> Iterator[LintIssue]:
    """No real personal data and no account IDs (CLAUDE.md, honesty rules)."""
    for subject, text in _strings(content):
        if "@" in text:
            yield LintIssue("email_like", subject, "'@' found: no email addresses in content")
        if _ACCOUNT_ID.search(text):
            yield LintIssue(
                "account_id_like", subject, "a 12-digit number looks like an account ID"
            )
