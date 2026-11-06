"""The only place raw AWS response dicts are read (ADR 0021, decision 3, and D1).

Each `clean_*` function turns one raw item into a frozen dataclass as it is received, and the
raw dict goes no further. What is dropped here can never be stored, logged or put in an error:
- env var values, so only the names are kept;
- the Lambda description's place in storage: it is kept for scoring in memory, never written;
- anything in a CloudTrail event beyond its source, name, time and the role that made the call.

Twelve-digit account IDs in every kept string become `<account>`, so an ARN in evidence is safe
to publish (M9). A malformed item raises `BoundaryError` with a fixed message and `from None`,
so neither the message nor the exception chain can carry a raw dict.

The raw shapes are the AWS response shapes, so one boundary serves both the recorded fixture and
the live collector.
"""

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
from typing import Annotated, Any, Literal
from urllib.parse import unquote

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from verity_core.model.enums import NodeType
from verity_core.model.ids import check_id

ACCOUNT_PLACEHOLDER = "<account>"
_ACCOUNT_ID = re.compile(r"(?<!\d)\d{12}(?!\d)")


class BoundaryError(ValueError):
    """A raw item was not the shape AWS documents. The message never holds any of its content."""


def scrub(text: str) -> str:
    """Replace every 12-digit number, which may be an account ID, with `<account>`."""
    return _ACCOUNT_ID.sub(ACCOUNT_PLACEHOLDER, text)


# --- clean records -------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectedFunction:
    name: str
    arn: str
    runtime: str
    handler: str
    role_arn: str
    architectures: tuple[str, ...]
    memory_mb: int
    timeout_s: int
    env_names: tuple[str, ...]  # names only, sorted
    code_sha256: str
    # Free text: scored, never stored (ADR 0021).
    description: str = field(default="", repr=False)


@dataclass(frozen=True)
class Statement:
    """One IAM policy statement. `negated` is a `NotAction` or `NotResource` statement, which
    the crawler ignores and reports as unparsed."""

    effect: str
    actions: tuple[str, ...]
    resources: tuple[str, ...]
    negated: bool = False


@dataclass(frozen=True)
class Trust:
    effect: str
    principals: tuple[str, ...]
    actions: tuple[str, ...]


@dataclass(frozen=True)
class Policy:
    name: str
    kind: Literal["inline", "managed"]
    statements: tuple[Statement, ...]


@dataclass(frozen=True)
class CollectedRole:
    name: str
    arn: str
    trust: tuple[Trust, ...]
    policies: tuple[Policy, ...]

    @property
    def statements(self) -> tuple[Statement, ...]:
        return tuple(s for p in self.policies for s in p.statements)


@dataclass(frozen=True)
class CollectedTable:
    name: str
    arn: str


@dataclass(frozen=True)
class CollectedManifest:
    name: str
    system: str
    functions: tuple[str, ...]  # names of the Lambda functions it lists


@dataclass(frozen=True)
class TrailEvent:
    event_source: str
    event_name: str
    event_time: datetime
    role_name: str | None


# --- helpers -------------------------------------------------------------------------------


def _guarded[**P, R](kind: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Turn any failure into a `BoundaryError` that says only which kind of record it was."""

    def decorate(clean: Callable[P, R]) -> Callable[P, R]:
        @wraps(clean)
        def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return clean(*args, **kwargs)
            except BoundaryError:
                raise
            except Exception:
                raise BoundaryError(f"malformed {kind} record") from None

        return guarded

    return decorate


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise BoundaryError("not text")
    return scrub(value)


def _texts(value: Any) -> tuple[str, ...]:
    """A string or a list of strings, as a sorted tuple without repeats."""
    if value is None:
        return ()
    items = [value] if isinstance(value, str) else value
    return tuple(sorted({_text(item) for item in items}))


def _document(value: Any) -> Mapping[str, Any]:
    """A policy document: a dict, or the URL-encoded JSON some APIs return."""
    if isinstance(value, str):
        value = json.loads(unquote(value))
    if not isinstance(value, Mapping):
        raise BoundaryError("not a document")
    return value


def _statement_list(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = document.get("Statement", [])
    return [raw] if isinstance(raw, Mapping) else list(raw)


def _effect(raw: Mapping[str, Any]) -> str:
    effect = raw["Effect"]
    if effect not in ("Allow", "Deny"):
        raise BoundaryError("unknown effect")
    return effect


def _statements(document: Any) -> tuple[Statement, ...]:
    found = []
    for raw in _statement_list(_document(document)):
        negated = "NotAction" in raw or "NotResource" in raw
        found.append(
            Statement(
                effect=_effect(raw),
                actions=_texts(raw.get("Action", raw.get("NotAction"))),
                resources=_texts(raw.get("Resource", raw.get("NotResource"))),
                negated=negated,
            )
        )
    return tuple(sorted(found, key=lambda s: (s.effect, s.actions, s.resources, s.negated)))


def _principals(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (_text(value),)
    if isinstance(value, Mapping):
        return tuple(sorted({p for v in value.values() for p in _texts(v)}))
    return ()


def _trust(document: Any) -> tuple[Trust, ...]:
    found = [
        Trust(_effect(raw), _principals(raw.get("Principal")), _texts(raw.get("Action")))
        for raw in _statement_list(_document(document))
    ]
    return tuple(sorted(found, key=lambda t: (t.effect, t.principals, t.actions)))


# --- cleaners ------------------------------------------------------------------------------


@_guarded("function")
def clean_function(raw: Mapping[str, Any]) -> CollectedFunction:
    variables = (raw.get("Environment") or {}).get("Variables") or {}
    return CollectedFunction(
        name=_text(raw["FunctionName"]),
        arn=_text(raw["FunctionArn"]),
        runtime=_text(raw.get("Runtime", "")),
        handler=_text(raw.get("Handler", "")),
        role_arn=_text(raw["Role"]),
        architectures=tuple(sorted(_text(a) for a in raw.get("Architectures", ()))),
        memory_mb=int(raw["MemorySize"]),
        timeout_s=int(raw["Timeout"]),
        env_names=tuple(sorted(_text(name) for name in variables)),  # the values stop here
        code_sha256=_text(raw.get("CodeSha256", "")),
        description=_text(raw.get("Description", "")),
    )


@_guarded("tag")
def clean_tags(mappings: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """`ResourceTagMappingList` into `{arn: {key: value}}`."""
    return {
        _text(item["ResourceARN"]): {_text(t["Key"]): _text(t["Value"]) for t in item["Tags"]}
        for item in mappings
    }


@_guarded("role")
def clean_role(
    raw: Mapping[str, Any],
    inline: Iterable[Mapping[str, Any]] = (),
    attached: Iterable[Mapping[str, Any]] = (),
) -> CollectedRole:
    """`raw` is a `ListRoles` item. Each inline policy is `{PolicyName, PolicyDocument}` and
    each attached one `{PolicyName, PolicyDocument}` with the managed policy's default version."""
    policies = [
        Policy(_text(p["PolicyName"]), "inline", _statements(p["PolicyDocument"])) for p in inline
    ] + [
        Policy(_text(p["PolicyName"]), "managed", _statements(p["PolicyDocument"]))
        for p in attached
    ]
    return CollectedRole(
        name=_text(raw["RoleName"]),
        arn=_text(raw["Arn"]),
        trust=_trust(raw["AssumeRolePolicyDocument"]),
        policies=tuple(sorted(policies, key=lambda p: (p.kind, p.name))),
    )


def clean_table(name: str, region: str) -> CollectedTable:
    """`ListTables` gives names only, so the ARN is built with the account left out."""
    return CollectedTable(
        name=name, arn=f"arn:aws:dynamodb:{region}:{ACCOUNT_PLACEHOLDER}:table/{name}"
    )


class _ManifestResource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: Literal["lambda"]
    name: Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]+$")]


class _Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    system: str
    resources: Annotated[list[_ManifestResource], Field(min_length=1)]

    @field_validator("system")
    @classmethod
    def _a_system_id(cls, value: str) -> str:
        return check_id(value, NodeType.AI_SYSTEM)


def clean_manifest(raw: Mapping[str, Any]) -> CollectedManifest | None:
    """A manifest from an SSM parameter `{Name, Value}`. Returns None if it is invalid, for the
    caller to count: one bad manifest never stops a run, and nothing of it is kept."""
    try:
        parsed = _Manifest.model_validate(yaml.safe_load(raw["Value"]))
        return CollectedManifest(
            name=_text(raw["Name"]),
            system=parsed.system,
            functions=tuple(sorted({r.name for r in parsed.resources})),
        )
    except (yaml.YAMLError, ValidationError, KeyError, TypeError, ValueError, AttributeError):
        return None


@_guarded("trail event")
def clean_trail_event(raw: Mapping[str, Any]) -> TrailEvent:
    """Only the source, name, time and calling role survive: the rest of a CloudTrail event can
    hold request parameters."""
    when = raw["EventTime"]
    if isinstance(when, str):
        when = datetime.fromisoformat(when)
    role = None
    detail = raw.get("CloudTrailEvent")
    if isinstance(detail, str):
        issuer = (
            json.loads(detail)
            .get("userIdentity", {})
            .get("sessionContext", {})
            .get("sessionIssuer")
        )
        role = _text(issuer["userName"]) if isinstance(issuer, Mapping) else None
    return TrailEvent(
        event_source=_text(raw["EventSource"]),
        event_name=_text(raw["EventName"]),
        event_time=when.astimezone(UTC),
        role_name=role,
    )
