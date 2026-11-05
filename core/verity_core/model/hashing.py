"""Canonical JSON and SHA-256 helpers.

Hashes must not depend on key order, whitespace or the timezone a timestamp was written in,
so every identity hash in the graph goes through these functions.
"""

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialise JSON-compatible data deterministically: sorted keys, no whitespace."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
