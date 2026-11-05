"""Canonical JSON and SHA-256 helpers.

Hashes must not depend on key order, whitespace or the timezone a timestamp was written in,
so every identity hash in the graph goes through these functions.
"""

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_json(value: Any) -> str:
    """Serialise JSON-compatible data deterministically: sorted keys, no whitespace."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


# Stamped by the repository on write, so they say nothing about whether content changed.
STAMPED_FIELDS = frozenset({"created_at", "updated_at", "version"})


def content_hash(record: BaseModel) -> str:
    """Hash of a record's content, used to detect real changes (D14). Re-upserting an
    unchanged record must write nothing, including no history entry."""
    return sha256_hex(canonical_json(record.model_dump(mode="json", exclude=STAMPED_FIELDS)))
