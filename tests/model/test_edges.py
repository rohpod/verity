from datetime import UTC, date, datetime

import pytest
from factories import COMMON, make_edge
from pydantic import ValidationError
from verity_core.model import ids
from verity_core.model.edges import AppliesToEdge, MapsToEdge, PlainEdge, parse_edge
from verity_core.model.enums import (
    EdgeType,
    Purpose,
    RationaleType,
    Role,
    StrmType,
    Sufficiency,
)

A, B = ids.person_id("a"), ids.system_id("b")
T0 = datetime(2026, 11, 5, tzinfo=UTC)
T1 = datetime(2026, 11, 6, tzinfo=UTC)


def test_there_are_27_edge_types():
    assert len(EdgeType) == 27


@pytest.mark.parametrize("edge_type", list(EdgeType))
def test_every_edge_type_round_trips_through_parse_edge(edge_type):
    edge = make_edge(edge_type, A, B)
    parsed = parse_edge(edge.model_dump(mode="json"))
    assert type(parsed) is type(edge)
    assert parsed == edge


def test_typed_edges_are_not_plain_edges():
    assert isinstance(make_edge(EdgeType.MAPS_TO, "req:a:b", "ctl:VC-1"), MapsToEdge)
    assert isinstance(make_edge(EdgeType.OWNS, A, B), PlainEdge)
    with pytest.raises(ValidationError):
        PlainEdge(src=A, dst=B, type=EdgeType.MAPS_TO, **COMMON)


def test_plain_edges_have_no_qualifier():
    edge = make_edge(EdgeType.OWNS, A, B)
    assert edge.qualifier is None
    assert edge.key == (A, EdgeType.OWNS, B, None)


def test_applies_to_is_one_edge_per_role():
    sys_id, req = ids.system_id("support-assistant"), ids.requirement_id("euaia", "art50-1")
    provider = make_edge(EdgeType.APPLIES_TO, req, sys_id, role=Role.PROVIDER)
    deployer = make_edge(EdgeType.APPLIES_TO, req, sys_id, role=Role.DEPLOYER)
    assert provider.key != deployer.key
    assert provider.qualifier == "provider" and deployer.qualifier == "deployer"


def test_processes_is_one_edge_per_purpose():
    s, d = ids.system_id("x"), ids.dataset_id("d")
    inference = make_edge(EdgeType.PROCESSES, s, d, purpose=Purpose.INFERENCE)
    training = make_edge(EdgeType.PROCESSES, s, d, purpose=Purpose.TRAINING)
    assert inference.key != training.key


def test_applies_to_status_is_not_stored():
    # in_force | upcoming is derived from as_of (D5), so the edge has no such field.
    with pytest.raises(ValidationError):
        make_edge(EdgeType.APPLIES_TO, "req:a:b", B, status="in_force")
    assert make_edge(EdgeType.APPLIES_TO, "req:a:b", B, in_force_from=date(2027, 12, 2))


def test_self_loops_are_rejected():
    with pytest.raises(ValidationError, match="itself"):
        make_edge(EdgeType.CALLS, "res:l:r:a", "res:l:r:a")


@pytest.mark.parametrize("bad", ["", "nope", "sys:a#b", "sys:"])
def test_bad_endpoint_ids_are_rejected(bad):
    with pytest.raises(ValidationError):
        make_edge(EdgeType.OWNS, A, bad)
    with pytest.raises(ValidationError):
        make_edge(EdgeType.OWNS, bad, B)


def test_unknown_fields_and_types_are_rejected():
    with pytest.raises(ValidationError):
        make_edge(EdgeType.OWNS, A, B, weight=3)
    with pytest.raises(ValidationError):
        parse_edge({"type": "LIKES", "src": A, "dst": B, **COMMON})


def maps(**overrides):
    return make_edge(EdgeType.MAPS_TO, "req:a:b", "ctl:VC-1", **overrides)


@pytest.mark.parametrize(
    "strm", [StrmType.EQUAL, StrmType.SUBSET_OF, StrmType.SUPERSET_OF, StrmType.INTERSECTS_WITH]
)
def test_real_relationships_need_strength_and_sufficiency(strm):
    assert maps(strm=strm).strength == 7
    with pytest.raises(ValidationError, match="needs a strength"):
        maps(strm=strm, strength=None)
    with pytest.raises(ValidationError, match="needs a strength"):
        maps(strm=strm, sufficiency=None)


def test_no_relationship_takes_no_strength_or_sufficiency():
    ok = maps(strm=StrmType.NO_RELATIONSHIP, strength=None, sufficiency=None)
    assert ok.strength is None and ok.sufficiency is None
    with pytest.raises(ValidationError, match="takes no strength"):
        maps(strm=StrmType.NO_RELATIONSHIP, sufficiency=Sufficiency.FULL, strength=None)
    with pytest.raises(ValidationError, match="takes no strength"):
        maps(strm=StrmType.NO_RELATIONSHIP, strength=5, sufficiency=None)


@pytest.mark.parametrize("strength", [0, 11, -1])
def test_strength_is_1_to_10(strength):
    with pytest.raises(ValidationError):
        maps(strength=strength)


def test_every_mapping_needs_a_rationale():
    with pytest.raises(ValidationError):
        maps(rationale="")
    with pytest.raises(ValidationError):
        MapsToEdge(
            src="req:a:b",
            dst="ctl:VC-1",
            strm=StrmType.EQUAL,
            strength=9,
            sufficiency=Sufficiency.FULL,
            rationale_type=RationaleType.SEMANTIC,
            **COMMON,
        )


def test_applies_to_needs_a_rule_and_a_reason():
    with pytest.raises(ValidationError):
        AppliesToEdge(src="req:a:b", dst=B, role=Role.ANY, rule_id="", reason="r", **COMMON)


def test_closed_intervals():
    edge = make_edge(EdgeType.OWNS, A, B, closed_intervals=((T0, T1),))
    assert edge.closed_intervals == ((T0, T1),)
    with pytest.raises(ValidationError, match="ends before"):
        make_edge(EdgeType.OWNS, A, B, closed_intervals=((T1, T0),))


def test_valid_to_cannot_precede_valid_from():
    with pytest.raises(ValidationError, match="valid_to"):
        make_edge(EdgeType.OWNS, A, B, valid_from=T1, valid_to=T0)
