"""The snapshot models, built from the public field lists (ADR 0029, decisions 3 and 11).

Each node and edge model is a copy of its source model restricted to the fields `fields.py`
publishes, so a field that is not listed cannot appear in the file. Evidence gains `redacted`,
which says the hash covers the published content and not the stored original (decision 6).
"""

import operator
from functools import reduce
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, create_model

from verity_core.export.fields import (
    PUBLIC_EDGE_FIELDS,
    PUBLIC_NODE_FIELDS,
    public_fields,
    unclassified,
)
from verity_core.model.base import UtcDatetime, VerityRecord
from verity_core.model.nodes import Evidence

SCHEMA_VERSION = 1
DataSource = Literal["live", "fixture"]


def _restricted(model: type[BaseModel]) -> type[VerityRecord]:
    """A frozen, strict copy of `model` with only its public fields. Validators are not carried
    over: the values were validated when the graph was built, and the snapshot only carries them.
    A model with a field that is neither public nor withheld is refused."""
    problems = unclassified(model)
    if any(problems.values()):
        raise ValueError(f"{model.__name__} has unclassified fields: {problems}")
    declared: dict[str, Any] = {
        name: (model.model_fields[name].annotation, model.model_fields[name])
        for name in public_fields(model)
    }
    if model is Evidence:
        declared["redacted"] = (bool, Field(default=False))
    return create_model(f"Snapshot{model.__name__}", __base__=VerityRecord, **declared)


NODE_MODELS: dict[type[BaseModel], type[VerityRecord]] = {
    model: _restricted(model) for model in PUBLIC_NODE_FIELDS
}
EDGE_MODELS: dict[type[BaseModel], type[VerityRecord]] = {
    model: _restricted(model) for model in PUBLIC_EDGE_FIELDS
}

SnapshotNode = Annotated[reduce(operator.or_, NODE_MODELS.values()), Field(discriminator="type")]
SnapshotEdge = Annotated[reduce(operator.or_, EDGE_MODELS.values()), Field(discriminator="type")]


class Snapshot(VerityRecord):
    """What `verity export` writes. Every field is derived from the graph or the run."""

    schema_version: Literal[1] = SCHEMA_VERSION
    data_source: DataSource  # `live` is the account; `fixture` is the recorded, simulated one
    as_of: UtcDatetime
    nodes: list[SnapshotNode]
    edges: list[SnapshotEdge]
