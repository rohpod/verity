import pytest
from factories import COMMON, one_of_each
from pydantic import ValidationError
from verity_core.model import ids
from verity_core.model.enums import (
    AssuranceLevel,
    ControlKind,
    ImplementationStatus,
    NodeType,
    ScopeLevel,
)
from verity_core.model.nodes import (
    AISystem,
    AWSResource,
    Control,
    ControlAssessment,
    Person,
    parse_node,
)

NODES = one_of_each()


def test_there_is_one_model_per_node_type():
    assert set(NODES) == set(NodeType)
    assert len(NODES) == 18


@pytest.mark.parametrize("node", NODES.values(), ids=[t.value for t in NODES])
def test_json_round_trip_through_parse_node(node):
    parsed = parse_node(node.model_dump(mode="json"))
    assert type(parsed) is type(node)
    assert parsed == node


@pytest.mark.parametrize("node", NODES.values(), ids=[t.value for t in NODES])
def test_id_prefix_must_match_the_node_type(node):
    other = NodeType.POLICY if node.type is not NodeType.POLICY else NodeType.RISK
    with pytest.raises(ValidationError, match="expected"):
        type(node).model_validate(node.model_dump() | {"id": ids.make_id(other, "x")})


@pytest.mark.parametrize("node", NODES.values(), ids=[t.value for t in NODES])
def test_unknown_fields_are_rejected(node):
    with pytest.raises(ValidationError):
        node.__class__.model_validate(node.model_dump() | {"email": "a@example.com"})


def test_person_cannot_hold_an_email_address():
    with pytest.raises(ValidationError):
        Person(id=ids.person_id("x"), name="X", email="x@example.com", **COMMON)


def test_parse_node_rejects_unknown_or_missing_type():
    with pytest.raises(ValidationError):
        parse_node({"type": "Spaceship", "id": "sys:x"})
    with pytest.raises(ValidationError):
        parse_node({"id": "sys:x"})


def test_required_fields_are_enforced():
    with pytest.raises(ValidationError):
        AISystem(id=ids.system_id("x"), name="X", **COMMON)  # no purpose or kind


def control(**overrides):
    fields = {
        "id": ids.control_id("VC-001"),
        "title": "T",
        "summary": "S",
        "kind": ControlKind.TECHNICAL,
        "automatable": True,
        "scope_level": ScopeLevel.SYSTEM,
        **COMMON,
    } | overrides
    return Control(**fields)


def test_technical_controls_can_be_automatable():
    assert control().automatable


@pytest.mark.parametrize("kind", [ControlKind.ORGANISATIONAL, ControlKind.LEGAL_DOCUMENTARY])
def test_only_technical_controls_can_be_automatable(kind):
    with pytest.raises(ValidationError, match="cannot be automatable"):
        control(kind=kind)
    assert not control(kind=kind, automatable=False).automatable


def assessment(**overrides):
    fields = {
        "id": ids.ca_id(ids.control_id("VC-001"), ids.system_id("x")),
        "status": ImplementationStatus.IMPLEMENTED,
        "assurance_level": AssuranceLevel.L3_TESTED,
        **COMMON,
    } | overrides
    return ControlAssessment(**fields)


def test_l4_needs_a_named_person():
    with pytest.raises(ValidationError, match="named assessor"):
        assessment(assurance_level=AssuranceLevel.L4_VERIFIED)
    verified = assessment(
        assurance_level=AssuranceLevel.L4_VERIFIED, assessor=ids.person_id("a-singh")
    )
    assert verified.assessor == "person:a-singh"


def test_assessor_must_be_a_person_id():
    with pytest.raises(ValidationError):
        assessment(assessor=ids.system_id("x"))


def test_assurance_levels_are_ordered():
    assert AssuranceLevel.L2_EVIDENCED < AssuranceLevel.L3_TESTED < AssuranceLevel.L4_VERIFIED


def test_no_model_shadows_an_envelope_field():
    # Requirement once declared `version: str`, silently replacing the revision counter.
    from verity_core.model.base import Envelope
    from verity_core.model.edges import AppliesToEdge, MapsToEdge, PlainEdge, ProcessesEdge

    classes = {type(n) for n in NODES.values()} | {
        MapsToEdge,
        AppliesToEdge,
        ProcessesEdge,
        PlainEdge,
    }
    for cls in classes:
        for name, field in Envelope.model_fields.items():
            assert cls.model_fields[name].annotation == field.annotation, (cls.__name__, name)


def resource(*names):
    return AWSResource(
        id="res:lambda:eu-north-1:x",
        resource_type="lambda",
        region="eu-north-1",
        name="x",
        env_var_names=list(names),
        **COMMON,
    )


def test_env_var_names_are_accepted():
    assert resource("OPENAI_BASE_URL", "_private", "lower1").env_var_names


@pytest.mark.parametrize("smuggled", ["API_KEY=sk-canary", "sk-canary", "https://x", "", "1ABC"])
def test_a_value_cannot_be_stored_as_an_env_var_name(smuggled):
    with pytest.raises(ValidationError):
        resource(smuggled)
