"""The scanner that has the last word on a snapshot (ADR 0029, decision 7).

It is written apart from the redaction: it imports nothing from it and shares none of its
patterns, so one mistake cannot pass both. It runs on the serialised output, parsed back, and
walks every key and every value. A hit means nothing is written.

It reports the category and the JSON path of a hit, never the value. A dict key can be the
sensitive value, so a key appears in a path only if the key itself scans clean.
"""

import json
import re
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from typing import Any

ACCOUNT_ID = "account_id"
DIGEST = "account_digest"
FUNCTION_URL = "function_url"
EMAIL = "email"
CANARY = "canary"
IDENTITY = "identity_or_path"
OLD_HASH = "old_hash"
INVALID = "invalid_json"

_TWELVE_DIGITS = re.compile(r"(?<!\d)\d{12}(?!\d)")
_THE_PLACEHOLDER = "000000000000"
_WHOLLY_A_HASH = re.compile(r"(?:[0-9a-f]{64}|ev:[0-9a-f]+)")
_DIGEST_TEXT = re.compile(r"acct_[0-9a-f]{8}")
_URL_PARTS = ("lambda-url.", ".on.aws", "execute-api.")
# `@`, a domain, and a final label of letters only, so `crawler@0.1.0` is not an address.
_EMAIL = re.compile(r"@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]+(?![A-Za-z0-9-])")
_CANARY = re.compile(r"VERITY-[A-Z-]*CANARY")
_USER_ARN = re.compile(r"arn:[^\s\"]*:user/")
_PATHS = ("/Users/", "/home/")
_SAFE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")


@dataclass(frozen=True)
class Hit:
    category: str
    path: str  # a JSON path such as `$.nodes[3].content.config.role`; never a value

    def __str__(self) -> str:
        return f"{self.category} at {self.path}"


def _categories(text: str, old_hashes: Collection[str]) -> list[str]:
    found = []
    digits = any(m.group() != _THE_PLACEHOLDER for m in _TWELVE_DIGITS.finditer(text))
    if digits and not _WHOLLY_A_HASH.fullmatch(text):
        found.append(ACCOUNT_ID)
    if _DIGEST_TEXT.search(text):
        found.append(DIGEST)
    if any(part in text for part in _URL_PARTS):
        found.append(FUNCTION_URL)
    if _EMAIL.search(text):
        found.append(EMAIL)
    if _CANARY.search(text):
        found.append(CANARY)
    if _USER_ARN.search(text) or any(part in text for part in _PATHS):
        found.append(IDENTITY)
    if any(old in text for old in old_hashes):
        found.append(OLD_HASH)
    return found


def _segment(key: str, position: int, old_hashes: Collection[str]) -> str:
    """A key as a path segment, or a placeholder if showing it could show a value."""
    if _SAFE_KEY.fullmatch(key) and not _categories(key, old_hashes):
        return f".{key}"
    return f".{{key {position}}}"


def _walk(value: Any, path: str, old: Collection[str]) -> Iterator[Hit]:
    if isinstance(value, dict):
        for position, key in enumerate(sorted(value, key=str)):
            segment = _segment(str(key), position, old)
            for category in _categories(str(key), old):
                yield Hit(category, path + segment)
            yield from _walk(value[key], path + segment, old)
    elif isinstance(value, list):
        for position, item in enumerate(value):
            yield from _walk(item, f"{path}[{position}]", old)
    elif isinstance(value, str):
        for category in _categories(value, old):
            yield Hit(category, path)
    elif isinstance(value, int | float) and not isinstance(value, bool):
        # A number can be an account ID too.
        for category in _categories(json.dumps(value), old):
            yield Hit(category, path)


def scan(data: Any, *, old_hashes: Collection[str] = ()) -> list[Hit]:
    """Every hit in parsed JSON. `old_hashes` are the sha256 values and IDs a redaction replaced;
    only a run that has the graph can supply them."""
    return list(_walk(data, "$", old_hashes))


def scan_text(text: str, *, old_hashes: Collection[str] = ()) -> list[Hit]:
    """Parses serialised JSON, so escaped forms are seen as they would be read, then scans it."""
    try:
        parsed = json.loads(text)
    except ValueError:
        return [Hit(INVALID, "$")]
    return scan(parsed, old_hashes=old_hashes)
