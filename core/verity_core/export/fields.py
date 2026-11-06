"""Which fields of each node and edge model are published (ADR 0029, decision 3).

A field is public or withheld, and a model field that is neither fails `unclassified`, so a field
added later is never published by default. The snapshot models are built from these lists.

Withheld, and why:
- `tenant`, `created_at`, `updated_at`, `version`: storage bookkeeping stamped on write. The
  snapshot's `as_of` and each record's own dates say what the UI needs.
- `config_hash`, `previous_config_hash`, `new_config_hash`: computed over raw configuration that
  includes the account digest, so a published hash lets a reader test candidate digests offline
  (decision 4). The UI needs only that a change happened.
"""

from pydantic import BaseModel

from verity_core.model.edges import AppliesToEdge, MapsToEdge, PlainEdge, ProcessesEdge
from verity_core.model.nodes import (
    AISystem,
    AWSResource,
    Candidate,
    ChangeEvent,
    Control,
    ControlAssessment,
    Dataset,
    Department,
    DiscoveryRun,
    Evidence,
    Framework,
    Model,
    Organisation,
    Person,
    Policy,
    Provider,
    Requirement,
    Risk,
)

# On every node and every edge.
PUBLIC_ENVELOPE = ("source", "confidence", "valid_from", "valid_to")
WITHHELD_ENVELOPE = ("tenant", "created_at", "updated_at", "version")

# Node fields beyond the envelope.
PUBLIC_NODE_FIELDS: dict[type[BaseModel], tuple[str, ...]] = {
    Organisation: ("id", "type", "name"),
    Department: ("id", "type", "name"),
    Person: ("id", "type", "name", "job_title"),
    AISystem: (
        "id",
        "type",
        "name",
        "purpose",
        "kind",
        "roles",
        "use_domains",
        "interacts_with_people",
        "generates_synthetic_content",
        "first_placed_on_market",
        "significant_change_on",
    ),
    Candidate: ("id", "type", "name", "ai_likelihood", "signals"),
    AWSResource: (
        "id",
        "type",
        "resource_type",
        "region",
        "name",
        "tags",
        "env_var_names",  # names only: the graph never holds a value (D1)
        "ai_likelihood",
        "signals",
    ),
    Model: ("id", "type", "name", "origin"),
    Provider: ("id", "type", "name", "simulated"),
    Dataset: ("id", "type", "name", "classification", "personal_data"),
    Risk: ("id", "type", "title", "description"),
    Control: ("id", "type", "title", "summary", "kind", "automatable", "scope_level"),
    ControlAssessment: (
        "id",
        "type",
        "status",
        "assurance_level",
        "method",
        "assessed_at",
        "assessor",
    ),
    Requirement: (
        "id",
        "type",
        "ref",
        "summary",
        "source_url",
        "source_version",
        "last_verified",
        "verified_against",
    ),
    Framework: ("id", "type", "name", "source_version", "source_url", "last_verified", "binding"),
    Evidence: (
        "id",
        "type",
        "subject",
        "kind",
        "collector",
        "collected_at",
        "valid_until",
        "content",
        "content_ref",
        "sha256",
    ),
    Policy: ("id", "type", "title", "summary"),
    DiscoveryRun: ("id", "type", "mode", "started_at", "finished_at", "crawler_version", "summary"),
    ChangeEvent: ("id", "type", "detected_at"),
}

WITHHELD_NODE_FIELDS: dict[type[BaseModel], tuple[str, ...]] = {
    AWSResource: ("config_hash",),
    ChangeEvent: ("previous_config_hash", "new_config_hash"),
}

# Edge fields beyond the envelope. `src`, `dst`, `type` and `closed_intervals` are on every edge.
_EDGE_BASE = ("src", "dst", "type", "closed_intervals")
PUBLIC_EDGE_FIELDS: dict[type[BaseModel], tuple[str, ...]] = {
    MapsToEdge: (*_EDGE_BASE, "strm", "strength", "rationale_type", "rationale", "sufficiency"),
    AppliesToEdge: (*_EDGE_BASE, "role", "rule_id", "reason", "in_force_from", "condition"),
    ProcessesEdge: (*_EDGE_BASE, "purpose"),
    PlainEdge: _EDGE_BASE,
}
WITHHELD_EDGE_FIELDS: dict[type[BaseModel], tuple[str, ...]] = {}

# Keys dropped at any depth from Evidence content: the same hash fields, inside the content
# (decision 4). Dropping one changes the content, so the Evidence is rebuilt (decision 6).
WITHHELD_CONTENT_KEYS = frozenset({"config_hash", "previous_config_hash", "new_config_hash"})


def public_fields(model: type[BaseModel]) -> tuple[str, ...]:
    """The published fields of a node or edge model, envelope included."""
    table = PUBLIC_NODE_FIELDS if model in PUBLIC_NODE_FIELDS else PUBLIC_EDGE_FIELDS
    return (*table[model], *PUBLIC_ENVELOPE)


def withheld_fields(model: type[BaseModel]) -> tuple[str, ...]:
    own = WITHHELD_NODE_FIELDS if model in PUBLIC_NODE_FIELDS else WITHHELD_EDGE_FIELDS
    return (*own.get(model, ()), *WITHHELD_ENVELOPE)


def unclassified(model: type[BaseModel]) -> dict[str, set[str]]:
    """Fields the model has that are neither public nor withheld (`missing`), fields listed that
    the model does not have (`unknown`), and fields listed as both (`both`). All empty is good."""
    declared = set(model.model_fields)
    public, withheld = set(public_fields(model)), set(withheld_fields(model))
    return {
        "missing": declared - public - withheld,
        "unknown": (public | withheld) - declared,
        "both": public & withheld,
    }


def all_models() -> tuple[type[BaseModel], ...]:
    return (*PUBLIC_NODE_FIELDS, *PUBLIC_EDGE_FIELDS)
