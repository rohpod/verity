"""Errors a repository raises. Rule violations (`InvalidEdgeError`, `InvalidNodeError`) come
from `verity_core.model.validation` and are re-exported here so callers import from one place."""

from verity_core.model.validation import (
    GraphValidationError,
    InvalidEdgeError,
    InvalidNodeError,
)

__all__ = [
    "EdgeClosedError",
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


class EdgeClosedError(RepositoryError):
    """The edge was closed. Reopening it arrives with `close_edge`."""
