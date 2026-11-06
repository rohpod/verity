"""Every model field is public or withheld, and never both (ADR 0029, decision 3)."""

import pytest
from pydantic import Field
from verity_core.export import fields
from verity_core.export.snapshot import EDGE_MODELS, NODE_MODELS, _restricted
from verity_core.model.nodes import AWSResource, ChangeEvent, Evidence, Organisation


@pytest.mark.parametrize("model", fields.all_models(), ids=lambda m: m.__name__)
def test_every_real_model_field_is_classified_once(model):
    problems = fields.unclassified(model)
    assert problems == {"missing": set(), "unknown": set(), "both": set()}


def test_every_node_and_edge_model_has_a_snapshot_model():
    assert set(NODE_MODELS) == set(fields.PUBLIC_NODE_FIELDS)
    assert set(EDGE_MODELS) == set(fields.PUBLIC_EDGE_FIELDS)
    assert len(NODE_MODELS) == 18


def test_a_new_field_in_neither_list_is_reported_and_refused():
    class WithANewField(Organisation):
        favourite_colour: str = Field(default="blue")

    # The lists are keyed by class, so give the subclass the parent's entry and nothing more.
    fields.PUBLIC_NODE_FIELDS[WithANewField] = fields.PUBLIC_NODE_FIELDS[Organisation]
    try:
        assert fields.unclassified(WithANewField)["missing"] == {"favourite_colour"}
        with pytest.raises(ValueError, match="unclassified"):
            _restricted(WithANewField)
    finally:
        del fields.PUBLIC_NODE_FIELDS[WithANewField]


def test_a_field_listed_but_not_on_the_model_is_reported():
    original = fields.PUBLIC_NODE_FIELDS[Organisation]
    fields.PUBLIC_NODE_FIELDS[Organisation] = (*original, "ghost")
    try:
        assert fields.unclassified(Organisation)["unknown"] == {"ghost"}
    finally:
        fields.PUBLIC_NODE_FIELDS[Organisation] = original


def test_the_config_hash_fields_are_withheld_everywhere():
    assert "config_hash" in fields.withheld_fields(AWSResource)
    assert {"previous_config_hash", "new_config_hash"} <= set(fields.withheld_fields(ChangeEvent))
    for model in fields.all_models():
        assert not {"config_hash", "previous_config_hash", "new_config_hash"} & set(
            fields.public_fields(model)
        )
    assert {
        "config_hash",
        "previous_config_hash",
        "new_config_hash",
    } == fields.WITHHELD_CONTENT_KEYS


def test_the_bookkeeping_fields_are_withheld_and_provenance_is_kept():
    for model in fields.all_models():
        assert {"tenant", "created_at", "updated_at", "version"} <= set(
            fields.withheld_fields(model)
        )
        assert {"source", "confidence"} <= set(fields.public_fields(model))


def test_the_snapshot_evidence_model_adds_redacted_and_nothing_else():
    extra = set(NODE_MODELS[Evidence].model_fields) - set(fields.public_fields(Evidence))
    assert extra == {"redacted"}
