"""Links functions to AI systems and decides which become Candidates (architecture section D,
stage 4; ADR 0021, decisions 12 to 14). Pure."""

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

from verity_core.content.schema import AiSignalsFile
from verity_core.discovery.boundary import CollectedFunction, CollectedManifest
from verity_core.discovery.signals import NAMES_UNKNOWN_SYSTEM, Score
from verity_core.model.enums import AiLikelihood

# An unlinked function becomes a Candidate when it scores at least this much. `declared` is
# not here: an unlinked function is declared only when it names a system that does not exist.
CANDIDATE_LEVELS = (AiLikelihood.CONFIRMED_USAGE, AiLikelihood.PROBABLE, AiLikelihood.POSSIBLE)


@dataclass(frozen=True)
class Link:
    systems: tuple[str, ...] = ()  # systems named by a tag or manifest that exist
    unknown: tuple[str, ...] = ()  # systems named that do not exist


@dataclass(frozen=True)
class CandidateSpec:
    function: str  # the function's name
    likelihood: AiLikelihood
    signals: tuple[str, ...]


def links(
    rules: AiSignalsFile,
    functions: Iterable[CollectedFunction],
    tags_by_arn: Mapping[str, Mapping[str, str]],
    manifests: Iterable[CollectedManifest],
    known_systems: Collection[str],
) -> dict[str, Link]:
    """By function name. The `ai:system-id` tag and a manifest both link; they may name different
    systems, and the function then runs both."""
    functions = list(functions)
    named: dict[str, set[str]] = {f.name: set() for f in functions}
    tag_rule = rules.rule("tag")
    if tag_rule is not None:
        for function in functions:
            value = tags_by_arn.get(function.arn, {}).get(tag_rule.key or "")
            if value:
                named[function.name].add(value)
    for manifest in manifests:
        for name in manifest.functions:
            if name in named:
                named[name].add(manifest.system)
    return {
        name: Link(
            systems=tuple(sorted(s for s in systems if s in known_systems)),
            unknown=tuple(sorted(s for s in systems if s not in known_systems)),
        )
        for name, systems in named.items()
    }


def in_manifest(manifests: Iterable[CollectedManifest]) -> set[str]:
    """Names of the functions any manifest lists."""
    return {name for m in manifests for name in m.functions}


def candidates(scores: Mapping[str, Score], found: Mapping[str, Link]) -> list[CandidateSpec]:
    """One per function that is not in the registry but looks like AI, or that names a system
    that does not exist. Sorted by function name."""
    specs = []
    for name in sorted(scores):
        link, scored = found.get(name, Link()), scores[name]
        if link.unknown:
            signals = tuple(sorted({*scored.signals, NAMES_UNKNOWN_SYSTEM}))
            specs.append(CandidateSpec(name, AiLikelihood.DECLARED, signals))
        elif not link.systems and scored.likelihood in CANDIDATE_LEVELS:
            specs.append(CandidateSpec(name, scored.likelihood, scored.signals))
    return specs
