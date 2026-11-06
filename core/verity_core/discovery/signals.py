"""Scores one Lambda function from the signals that fired (architecture section D, stage 3).
Pure: the rules come from `content/rules/ai_signals.yaml` and the facts are passed in.

The ladder is declared, confirmed_usage, probable, possible, none. The strongest signal wins and
every signal that fired is kept, sorted, so the UI can say why (ADR 0021, decision 16).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from verity_core.content.schema import AiSignalsFile
from verity_core.discovery.boundary import CollectedFunction
from verity_core.model.enums import AiLikelihood

PLATFORM_COMPONENT = "platform_component"
NAMES_UNKNOWN_SYSTEM = "names_unknown_system"

LADDER = (
    AiLikelihood.DECLARED,
    AiLikelihood.CONFIRMED_USAGE,
    AiLikelihood.PROBABLE,
    AiLikelihood.POSSIBLE,
)
_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_CAMEL_LOWER_UPPER = re.compile(r"([a-z0-9])([A-Z])")
_CAMEL_UPPER_RUN = re.compile(r"([A-Z]+)([A-Z][a-z])")


@dataclass(frozen=True)
class Score:
    likelihood: AiLikelihood
    signals: tuple[str, ...]


def tokens(text: str) -> list[str]:
    """Whole words, lower case, split on anything that is not a letter or a digit and at
    CamelCase boundaries: `OpenAiProxy` and `OpenAIProxy` both give open, ai, proxy."""
    spaced = _CAMEL_LOWER_UPPER.sub(r"\1 \2", text)
    spaced = _CAMEL_UPPER_RUN.sub(r"\1 \2", spaced)
    return [t for t in _TOKEN_SPLIT.split(spaced.lower()) if t]


def score(
    rules: AiSignalsFile,
    function: CollectedFunction,
    tags: Mapping[str, str],
    *,
    in_manifest: bool,
    iam_ai_action: bool,
    usage: bool,
    trail_event: bool,
) -> Score:
    """The last four arguments are facts found elsewhere: a manifest lists the function, its
    role grants an AI action, its system has usage records, CloudTrail shows its role calling AI.
    A platform component, which has the platform tag and a name in `platform_functions`, scores
    none whatever else fires. The tag alone does nothing (ADR 0022)."""
    if rules.platform_tag in tags and function.name in rules.platform_functions:
        return Score(AiLikelihood.NONE, (PLATFORM_COMPONENT,))

    fired: dict[str, AiLikelihood] = {}
    for rule in rules.signals:
        hit = False
        match rule.kind:
            case "tag":
                hit = bool(tags.get(rule.key or ""))
            case "manifest":
                hit = in_manifest
            case "usage_record":
                hit = usage
            case "trail_event":
                hit = trail_event
            case "iam_action":
                hit = iam_ai_action
            case "env_name":
                pattern = re.compile(rule.pattern or "", re.IGNORECASE)
                hit = any(pattern.search(name) for name in function.env_names)
            case "name":
                pattern = re.compile(rule.pattern or "", re.IGNORECASE)
                words = tokens(function.name) + tokens(function.description)
                hit = any(pattern.fullmatch(word) for word in words)
        if hit:
            fired[rule.id] = rule.likelihood

    for level in LADDER:
        if level in fired.values():
            return Score(level, tuple(sorted(fired)))
    return Score(AiLikelihood.NONE, ())
