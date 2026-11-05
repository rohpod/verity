"""The Evidence node and its identity rule (D4, ADR 0010 and 0012).

The ID hashes subject, collector, `collected_at` and the content hash, so collecting
identical content again creates a new node. `sha256` stays a pure content hash.
Evidence is immutable: the repository refuses to change an existing one.
"""

from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Literal

from pydantic import Field, model_validator

from verity_core.model.base import NodeBase, UtcDatetime
from verity_core.model.enums import EvidenceKind, NodeType
from verity_core.model.hashing import canonical_json, sha256_hex
from verity_core.model.ids import check_id, node_type_of

EVIDENCE_ID_HEX_LENGTH = 32  # 128 bits
# Inline content cap in bytes of canonical JSON. M2 may lower it from measured item sizes (D14).
INLINE_EVIDENCE_MAX_BYTES = 50 * 1024
_AUTOMATED_COLLECTOR_PREFIXES = ("crawler@", "cli@")


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


class Evidence(NodeBase):
    """An immutable artefact. `valid_until` is how long it stays fresh; it is not the
    envelope `valid_to`, which ends the record's existence in the graph."""

    type: Literal[NodeType.EVIDENCE] = NodeType.EVIDENCE
    subject: str  # the node this is about; an ABOUT edge records the same link
    kind: EvidenceKind
    collector: str  # crawler@<ver>, cli@<ver> or person:<id>
    collected_at: UtcDatetime
    valid_until: UtcDatetime
    content: dict[str, Any] | None = None  # inline JSON, up to INLINE_EVIDENCE_MAX_BYTES
    content_ref: str | None = None  # git-versioned file under evidence/
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _check_identity_and_content(self) -> "Evidence":
        node_type_of(self.subject)
        self._check_collector()
        if self.valid_until <= self.collected_at:
            raise ValueError("valid_until must be after collected_at")
        if (self.content is None) == (self.content_ref is None):
            raise ValueError("give exactly one of content and content_ref")
        if self.content is not None:
            if len(canonical_json(self.content).encode()) > INLINE_EVIDENCE_MAX_BYTES:
                raise ValueError(f"inline content is over {INLINE_EVIDENCE_MAX_BYTES} bytes")
            if self.sha256 != content_sha256(self.content):
                raise ValueError("sha256 does not match the inline content")
        else:
            self._check_content_ref(self.content_ref)
        expected = evidence_id(self.subject, self.collector, self.collected_at, self.sha256)
        if self.id != expected:
            raise ValueError(f"id {self.id!r} does not match its hashed fields ({expected})")
        return self

    def _check_collector(self) -> None:
        if self.collector.startswith("person:"):
            check_id(self.collector, NodeType.PERSON)
        elif not (
            self.collector.startswith(_AUTOMATED_COLLECTOR_PREFIXES)
            and len(self.collector.partition("@")[2]) > 0
        ):
            raise ValueError("collector must be crawler@<ver>, cli@<ver> or person:<id>")

    @staticmethod
    def _check_content_ref(ref: str | None) -> None:
        path = PurePosixPath(ref or "")
        if path.is_absolute() or ".." in path.parts or path.parts[:1] != ("evidence",):
            raise ValueError("content_ref must be a relative path under evidence/")

    @classmethod
    def build(
        cls,
        *,
        subject: str,
        collector: str,
        collected_at: datetime,
        content: dict[str, Any] | None = None,
        content_ref: str | None = None,
        file_sha256: str | None = None,
        **fields: Any,
    ) -> "Evidence":
        """Compute `sha256` and `id`. A `content_ref` needs the file's hash as `file_sha256`."""
        if content is not None and content_ref is None:
            digest = content_sha256(content)
        elif file_sha256 is not None:
            digest = file_sha256
        else:
            raise ValueError("give inline content, or a content_ref with file_sha256")
        return cls(
            id=evidence_id(subject, collector, collected_at, digest),
            subject=subject,
            collector=collector,
            collected_at=collected_at,
            content=content,
            content_ref=content_ref,
            sha256=digest,
            **fields,
        )
