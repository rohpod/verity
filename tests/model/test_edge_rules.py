"""Tier 2 rejection: which writes the graph refuses (ADR 0012)."""

import pytest
from factories import COMMON, T0, make_edge, one_of_each, rule_nodes, twin
from verity_core.model import ids
from verity_core.model.enums import EdgeType, ModelOrigin, NodeType
from verity_core.model.nodes import AWSResource, Model, Organisation
from verity_core.model.validation import (
    EDGE_RULES,
    InvalidEdgeError,
    InvalidNodeError,
    validate_edge,
    validate_node_change,
)

NODES = rule_nodes()


def endpoints(src_type, dst_type):
    src = NODES[src_type]
    dst = NODES[dst_type] if src_type is not dst_type else twin(NODES[dst_type])
    return src, dst


def test_every_edge_type_has_a_rule():
    assert set(EDGE_RULES) == set(EdgeType)


@pytest.mark.parametrize("edge_type", list(EdgeType))
def test_only_the_listed_node_type_pairs_are_accepted(edge_type):
    allowed = EDGE_RULES[edge_type].pairs
    for src_type in NodeType:
        for dst_type in NodeType:
            src, dst = endpoints(src_type, dst_type)
            edge = make_edge(edge_type, src.id, dst.id)
            if (src_type, dst_type) in allowed:
                validate_edge(edge, src, dst)
            else:
                with pytest.raises(InvalidEdgeError) as caught:
                    validate_edge(edge, src, dst)
                assert caught.value.rule == "endpoint_types"


def rejects(rule, *args, **kwargs):
    with pytest.raises(InvalidEdgeError) as caught:
        validate_edge(*args, **kwargs)
    assert caught.value.rule == rule


def test_provided_by_on_an_in_house_model_is_rejected():
    in_house = NODES[NodeType.MODEL].model_copy(update={"origin": ModelOrigin.IN_HOUSE})
    provider = NODES[NodeType.PROVIDER]
    edge = make_edge(EdgeType.PROVIDED_BY, in_house.id, provider.id)
    rejects("provided_by_third_party_only", edge, in_house, provider)
    validate_edge(edge, NODES[NodeType.MODEL], provider)  # third-party is fine


def test_flipping_a_provided_model_to_in_house_is_rejected():
    model, provider = NODES[NodeType.MODEL], NODES[NodeType.PROVIDER]
    provided_by = make_edge(EdgeType.PROVIDED_BY, model.id, provider.id)
    flipped = model.model_copy(update={"origin": ModelOrigin.IN_HOUSE})
    with pytest.raises(InvalidEdgeError) as caught:
        validate_node_change(flipped, open_edges=[provided_by])
    assert caught.value.rule == "provided_by_third_party_only"
    validate_node_change(flipped)  # no open PROVIDED_BY edge, so allowed
    validate_node_change(model, open_edges=[provided_by])  # still third-party


def test_assumes_must_target_an_iam_role():
    function = AWSResource(
        id=ids.resource_id("lambda", "eu-north-1", "f"),
        resource_type="lambda",
        region="eu-north-1",
        name="f",
        **COMMON,
    )
    role = NODES[NodeType.AWS_RESOURCE]
    validate_edge(make_edge(EdgeType.ASSUMES, function.id, role.id), function, role)
    other = twin(function)
    rejects(
        "assumes_target_is_role",
        make_edge(EdgeType.ASSUMES, function.id, other.id),
        function,
        other,
    )


def test_changing_a_role_into_a_non_role_while_assumed_is_rejected():
    role = NODES[NodeType.AWS_RESOURCE]
    assumes = make_edge(EdgeType.ASSUMES, "res:lambda:eu-north-1:f", role.id)
    renamed = role.model_copy(update={"resource_type": "lambda"})
    with pytest.raises(InvalidEdgeError) as caught:
        validate_node_change(renamed, open_edges=[assumes])
    assert caught.value.rule == "assumes_target_is_role"


@pytest.mark.parametrize("edge_type", [EdgeType.ASSESSES, EdgeType.SCOPED_TO])
def test_a_control_assessment_has_one_control_and_one_scope(edge_type):
    ca = NODES[NodeType.CONTROL_ASSESSMENT]
    targets = (
        [NODES[NodeType.CONTROL]]
        if edge_type is EdgeType.ASSESSES
        else [NODES[NodeType.AI_SYSTEM], NODES[NodeType.ORGANISATION]]
    )
    first, second = targets[0], twin(targets[0])
    existing = make_edge(edge_type, ca.id, first.id)
    validate_edge(existing, ca, first)
    validate_edge(existing, ca, first, open_out_edges=[existing])  # re-upsert of the same edge
    rejects(
        "max_out", make_edge(edge_type, ca.id, second.id), ca, second, open_out_edges=[existing]
    )


def test_max_out_ignores_other_edge_types():
    ca, control, system = (
        NODES[t] for t in (NodeType.CONTROL_ASSESSMENT, NodeType.CONTROL, NodeType.AI_SYSTEM)
    )
    scoped = make_edge(EdgeType.SCOPED_TO, ca.id, system.id)
    validate_edge(make_edge(EdgeType.ASSESSES, ca.id, control.id), ca, control, [scoped])


def test_applies_to_has_an_edge_per_role_and_no_max():
    from verity_core.model.enums import Role

    req, system = NODES[NodeType.REQUIREMENT], NODES[NodeType.AI_SYSTEM]
    provider = make_edge(EdgeType.APPLIES_TO, req.id, system.id, role=Role.PROVIDER)
    deployer = make_edge(EdgeType.APPLIES_TO, req.id, system.id, role=Role.DEPLOYER)
    validate_edge(deployer, req, system, open_out_edges=[provider])


def test_missing_endpoint():
    src, dst = NODES[NodeType.PERSON], NODES[NodeType.AI_SYSTEM]
    edge = make_edge(EdgeType.OWNS, src.id, dst.id)
    rejects("missing_endpoint", edge, src, None)
    rejects("missing_endpoint", edge, None, dst)


def test_an_open_edge_cannot_touch_an_ended_node():
    src, dst = NODES[NodeType.PERSON], NODES[NodeType.AI_SYSTEM]
    ended = dst.model_copy(update={"valid_to": T0})
    rejects("endpoint_ended", make_edge(EdgeType.OWNS, src.id, dst.id), src, ended)
    # A historic edge that was itself closed is a true record of the past.
    validate_edge(make_edge(EdgeType.OWNS, src.id, dst.id, valid_to=T0), src, ended)


def test_passed_nodes_must_be_the_edges_endpoints():
    src, dst = NODES[NodeType.PERSON], NODES[NodeType.AI_SYSTEM]
    rejects("endpoint_mismatch", make_edge(EdgeType.OWNS, src.id, ids.system_id("other")), src, dst)


def test_edges_cannot_cross_tenants():
    src, dst = NODES[NodeType.PERSON], NODES[NodeType.AI_SYSTEM]
    other = dst.model_copy(update={"tenant": "other"})
    rejects("tenant_mismatch", make_edge(EdgeType.OWNS, src.id, dst.id), src, other)
    rejects("tenant_mismatch", make_edge(EdgeType.OWNS, src.id, dst.id, tenant="other"), src, dst)


def test_a_tenant_has_exactly_one_organisation():
    org = one_of_each()[NodeType.ORGANISATION]
    validate_node_change(org)
    validate_node_change(org, organisation_ids=[org.id])  # updating the one it has
    second = Organisation(id=ids.organisation_id("other"), name="Other", **COMMON)
    with pytest.raises(InvalidNodeError) as caught:
        validate_node_change(second, organisation_ids=[org.id])
    assert caught.value.rule == "organisation_per_tenant"


def test_errors_name_the_rule():
    with pytest.raises(InvalidEdgeError, match="^endpoint_types:"):
        src, dst = NODES[NodeType.RISK], NODES[NodeType.PERSON]
        validate_edge(make_edge(EdgeType.OWNS, src.id, dst.id), src, dst)


def test_model_and_aws_resource_fixtures_isolate_the_pair_rule():
    assert isinstance(NODES[NodeType.MODEL], Model)
    assert NODES[NodeType.MODEL].origin is ModelOrigin.THIRD_PARTY
    assert NODES[NodeType.AWS_RESOURCE].resource_type == "iam-role"


def test_only_models_and_resources_look_at_a_nodes_edges():
    # DynamoDBRepository skips reading a node's edges for every other type. If a new rule made
    # another type depend on its edges, that repository would miss it, and this fails first.
    every_edge = [make_edge(edge_type, "person:a", "sys:b") for edge_type in EdgeType] + [
        make_edge(EdgeType.ASSUMES, "res:lambda:r:f", "res:iam-role:global:r")
    ]
    for node_type, node in one_of_each().items():
        if node_type in (NodeType.MODEL, NodeType.AWS_RESOURCE):
            continue
        validate_node_change(node, open_edges=every_edge)
