"""Errors a repository raises. Rule violations (`InvalidEdgeError`, `InvalidNodeError`) come
from `verity_core.model.validation` and are re-exported here so callers import from one place."""

from verity_core.model.validation import (
    GraphValidationError,
    InvalidEdgeError,
    InvalidNodeError,
)

__all__ = [
    "ConcurrentWriteError",
    "EdgeNotFoundError",
    "GraphValidationError",
    "ImmutableNodeError",
    "InvalidEdgeError",
    "InvalidNodeError",
    "RepositoryError",
    "TenantMismatchError",
]


class RepositoryError(Exception):
    pass


class TenantMismatchError(RepositoryError):
    """A record belongs to another tenant than the repository."""


class ImmutableNodeError(RepositoryError):
    """Evidence is immutable. Collecting again creates a new node."""


class EdgeNotFoundError(RepositoryError):
    """No edge with that source, type, target and qualifier."""


class ConcurrentWriteError(RepositoryError):
    """Another writer changed the record after it was read, so this write was refused instead
    of overwriting theirs. Read again and retry (ADR 0013)."""
