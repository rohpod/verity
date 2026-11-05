"""Evidence identity (D4, docs/adr/0010 and 0012).

The ID hashes subject, collector, `collected_at` and the content hash, so collecting
identical content again creates a new node. `sha256` stays a pure content hash.
The Evidence node itself arrives with the other node models.
"""

from datetime import UTC, datetime
from typing import Any

from verity_core.model.hashing import canonical_json, sha256_hex

EVIDENCE_ID_HEX_LENGTH = 32  # 128 bits


def content_sha256(content: Any) -> str:
    """Pure content hash of inline evidence content."""
    return sha256_hex(canonical_json(content))


def evidence_id(subject: str, collector: str, collected_at: datetime, content_hash: str) -> str:
    """`ev:<32 hex>`. `content_hash` is `content_sha256(...)`, or a `content_ref` file hash."""
    if collected_at.tzinfo is None:
        raise ValueError("collected_at must be timezone-aware")
    # A JSON array keeps field boundaries unambiguous ("a"+"bc" differs from "ab"+"c").
    stamp = collected_at.astimezone(UTC).isoformat(timespec="microseconds")
    digest = sha256_hex(canonical_json([subject, collector, stamp, content_hash]))
    return f"ev:{digest[:EVIDENCE_ID_HEX_LENGTH]}"
