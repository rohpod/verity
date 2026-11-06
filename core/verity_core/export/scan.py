"""The scanner that has the last word on a snapshot (ADR 0029, decision 7; ADR 0030).

It is written apart from the redaction: it imports nothing from it and shares none of its
patterns, so one mistake cannot pass both. It runs on the serialised output, parsed back, and
walks every key and every value. A hit means nothing is written.

Each text is read as it stands, percent-decoded and Unicode-normalised, and matching ignores
case, so a value cannot pass by its spelling. Only a value that is exactly a hash is exempt from
the digit rule: a 64-hex value under a hash key, a 40-hex commit SHA under `commit_sha`, or an
Evidence or ChangeEvent ID of exactly its shape.

It reports the category and the JSON path of a hit, never the value. A dict key can be the
sensitive value, so a key appears in a path only if the key itself scans clean.
"""

import json
import math
import re
import unicodedata
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

ACCOUNT_ID = "account_id"
DIGEST = "account_digest"
FUNCTION_URL = "function_url"
EMAIL = "email"
CANARY = "canary"
IDENTITY = "identity_or_path"
AWS_KEY_ID = "aws_key_id"
OLD_HASH = "old_hash"
INVALID = "invalid_json"

_DIGIT_RUN = re.compile(r"\d{12,}")
_GROUPED_DIGITS = re.compile(r"(?<!\d)\d{4}[- ]\d{4}[- ]\d{4}(?!\d)")
_THE_PLACEHOLDER = "000000000000"
_HASH_KEYS = frozenset({"sha256", "file_sha256"})
_A_HASH = re.compile(r"[0-9a-f]{64}")
_A_COMMIT = re.compile(r"[0-9a-f]{40}")
_AN_EVIDENCE_ID = re.compile(r"ev:[0-9a-f]{32}")
_A_CHANGE_ID = re.compile(r"chg:\d{8}T\d{6}\.\d{6}Z:[0-9a-f]{16}")
_DIGEST_TEXT = re.compile(r"acct[_-]?[0-9a-f]{8}", re.IGNORECASE)
_URL_PARTS = ("lambda-url.", ".on.aws", "execute-api.")
# `@` and a dotted domain with a letter in it, so `crawler@0.1.0` is not an address.
_EMAIL = re.compile(r"@[\w-]+(?:\.[\w-]+)+")
_CANARY = re.compile(r"VERITY-[A-Z-]*CANARY", re.IGNORECASE)
_PERSON_ARN = re.compile(r"arn:[^\s\"]*:(?:user|assumed-role|federated-user)/", re.IGNORECASE)
_PATHS = ("/Users/", "/home/", "/root/", "/private/", "/var/folders/", "C:\\Users\\")
_KEY_ID = re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA|AROA|AIDA|ANPA|ANVA)[A-Z0-9]{16}(?![A-Z0-9])")
_HEX_RUN = re.compile(r"[0-9a-f]{12,}")
_OLD_WINDOW = 12  # a run of this many hex digits from a replaced hash is that hash, in part
_SAFE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


@dataclass(frozen=True)
class Hit:
    category: str
    path: str  # a JSON path such as `$.nodes[3].content.config.role`; never a value

    def __str__(self) -> str:
        return f"{self.category} at {self.path}"


@dataclass(frozen=True)
class _Old:
    """Replaced hashes, ready to be found whole, in part, or in another case."""

    whole: frozenset[str]
    windows: frozenset[str]

    @classmethod
    def of(cls, hashes: Collection[str]) -> "_Old":
        whole = frozenset(h.lower() for h in hashes)
        windows = set()
        for item in whole:
            digits = item.removeprefix("ev:")
            windows |= {digits[i : i + _OLD_WINDOW] for i in range(len(digits) - _OLD_WINDOW + 1)}
        return cls(whole, frozenset(windows))

    def found_in(self, text: str) -> bool:
        lowered = text.lower()
        if any(item in lowered for item in self.whole):
            return True
        return any(
            run[i : i + _OLD_WINDOW] in self.windows
            for run in _HEX_RUN.findall(lowered)
            for i in range(len(run) - _OLD_WINDOW + 1)
        )


def _forms(text: str) -> list[str]:
    """The text, and what it becomes when decoded, each Unicode-normalised."""
    forms = [text]
    for _ in range(3):
        decoded = unquote(forms[-1])
        if decoded == forms[-1]:
            break
        forms.append(decoded)
    return [unicodedata.normalize("NFKC", form) for form in forms]


def _exempt_from_digits(text: str, key: str) -> bool:
    if _AN_EVIDENCE_ID.fullmatch(text) or _A_CHANGE_ID.fullmatch(text):
        return True
    if key == "commit_sha":
        return _A_COMMIT.fullmatch(text) is not None
    return key in _HASH_KEYS and _A_HASH.fullmatch(text) is not None


def _has_account_digits(form: str) -> bool:
    runs = (m.group() != _THE_PLACEHOLDER for m in _DIGIT_RUN.finditer(form))
    return any(runs) or _GROUPED_DIGITS.search(form) is not None


def _has_email(form: str) -> bool:
    return any(any(c.isalpha() for c in m.group()) for m in _EMAIL.finditer(form))


def _categories(text: str, old: _Old, key: str = "") -> list[str]:
    found: set[str] = set()
    for form in _forms(text):
        lowered = form.lower()
        if _has_account_digits(form) and not _exempt_from_digits(text, key):
            found.add(ACCOUNT_ID)
        if _DIGEST_TEXT.search(form):
            found.add(DIGEST)
        if any(part in lowered for part in _URL_PARTS):
            found.add(FUNCTION_URL)
        if _has_email(form):
            found.add(EMAIL)
        if _CANARY.search(form):
            found.add(CANARY)
        if _PERSON_ARN.search(form) or any(part in form for part in _PATHS):
            found.add(IDENTITY)
        if _KEY_ID.search(form):
            found.add(AWS_KEY_ID)
        if old.found_in(form):
            found.add(OLD_HASH)
    return sorted(found)


def _segment(key: str, position: int, old: _Old) -> str:
    """A key as a path segment, or a placeholder if showing it could show a value."""
    if _SAFE_KEY.fullmatch(key) and not _categories(key, old):
        return f".{key}"
    return f".{{key {position}}}"


def _number_text(value: int | float) -> str:
    """A number as digits, if it is whole: the digits of a fraction are not an account ID."""
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return ""
        value = int(value)
    return str(abs(value))


def _walk(value: Any, path: str, old: _Old, key: str = "") -> Iterator[Hit]:
    if isinstance(value, dict):
        for position, name in enumerate(sorted(value, key=str)):
            segment = _segment(str(name), position, old)
            for category in _categories(str(name), old):
                yield Hit(category, path + segment)
            yield from _walk(value[name], path + segment, old, str(name))
    elif isinstance(value, list):
        for position, item in enumerate(value):
            yield from _walk(item, f"{path}[{position}]", old)
    elif isinstance(value, str):
        for category in _categories(value, old, key):
            yield Hit(category, path)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        # A number can be an account ID too.
        for category in _categories(_number_text(value), old):
            yield Hit(category, path)


def scan(data: Any, *, old_hashes: Collection[str] = ()) -> list[Hit]:
    """Every hit in parsed JSON. `old_hashes` are the hashes and IDs a redaction replaced or
    withheld; only a run that has the graph can supply them."""
    return list(_walk(data, "$", _Old.of(old_hashes)))


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A repeated key would hide the first value from the walk, but not from the file."""
    found = dict(pairs)
    if len(found) != len(pairs):
        raise ValueError("a key is repeated")
    return found


def _no_constant(name: str) -> None:
    raise ValueError(f"{name} is not JSON")


def scan_text(text: str, *, old_hashes: Collection[str] = ()) -> list[Hit]:
    """Parses serialised JSON, so escaped forms are seen as they would be read, then scans it."""
    try:
        parsed = json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_no_constant)
    except ValueError:
        return [Hit(INVALID, "$")]
    return scan(parsed, old_hashes=old_hashes)
