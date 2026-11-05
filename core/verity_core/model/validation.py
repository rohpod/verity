"""Write-time validation (tier 2 of edge rejection, ADR 0012).

Pure functions: they take the nodes and edges they need and touch no storage, so
`InMemoryRepository` and `DynamoDBRepository` run exactly the same rules. A consequence is
that nodes must be written before the edges that connect them.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from verity_core.model.edges import Edge
from verity_core.model.enums import EdgeType, ModelOrigin, NodeType
from verity_core.model.nodes import AWSResource, Model, Node

IAM_ROLE_RESOURCE_TYPE = "iam-role"


class GraphValidationError(ValueError):
    """A write the graph's rules refuse. `rule` names the rule, so tests and logs can say which."""

    def __init__(self, rule: str, message: str):
        super().__init__(f"{rule}: {message}")
        self.rule = rule


class InvalidEdgeError(GraphValidationError):
    pass


class InvalidNodeError(GraphValidationError):
    pass


@dataclass(frozen=True)
class EdgeRule:
    pairs: frozenset[tuple[NodeType, NodeType]]  # allowed (source type, target type)
    max_out: int | None = None  # most open edges of this type one source may have


def _rule(*pairs: tuple[NodeType, NodeType], max_out: int | None = None) -> EdgeRule:
    return EdgeRule(frozenset(pairs), max_out)


N = NodeType
EDGE_RULES: dict[EdgeType, EdgeRule] = {
    EdgeType.MEMBER_OF: _rule((N.PERSON, N.DEPARTMENT)),
    EdgeType.PART_OF: _rule(
        (N.DEPARTMENT, N.ORGANISATION), (N.REQUIREMENT, N.FRAMEWORK), (N.REQUIREMENT, N.REQUIREMENT)
    ),
    EdgeType.OWNS: _rule((N.PERSON, N.AI_SYSTEM), (N.PERSON, N.RISK)),
    EdgeType.DEVELOPS: _rule((N.PERSON, N.AI_SYSTEM)),
    EdgeType.APPROVES_RISK_FOR: _rule((N.PERSON, N.AI_SYSTEM)),
    EdgeType.RUNS_ON: _rule((N.AI_SYSTEM, N.AWS_RESOURCE)),
    EdgeType.ASSUMES: _rule((N.AWS_RESOURCE, N.AWS_RESOURCE)),
    EdgeType.CALLS: _rule((N.AWS_RESOURCE, N.AWS_RESOURCE)),
    EdgeType.USES_MODEL: _rule((N.AI_SYSTEM, N.MODEL)),
    EdgeType.PROVIDED_BY: _rule((N.MODEL, N.PROVIDER)),
    EdgeType.PROCESSES: _rule((N.AI_SYSTEM, N.DATASET)),
    EdgeType.TRAINED_ON: _rule((N.MODEL, N.DATASET)),
    EdgeType.DERIVED_FROM: _rule((N.CANDIDATE, N.AWS_RESOURCE)),
    EdgeType.PROMOTED_TO: _rule((N.CANDIDATE, N.AI_SYSTEM)),
    EdgeType.HAS_RISK: _rule((N.AI_SYSTEM, N.RISK)),
    EdgeType.MITIGATED_BY: _rule((N.RISK, N.CONTROL)),
    EdgeType.MAPS_TO: _rule((N.REQUIREMENT, N.CONTROL)),
    EdgeType.APPLIES_TO: _rule((N.REQUIREMENT, N.AI_SYSTEM), (N.REQUIREMENT, N.ORGANISATION)),
    EdgeType.ASSESSES: _rule((N.CONTROL_ASSESSMENT, N.CONTROL), max_out=1),
    EdgeType.SCOPED_TO: _rule(
        (N.CONTROL_ASSESSMENT, N.AI_SYSTEM),
        (N.CONTROL_ASSESSMENT, N.ORGANISATION),
        (N.CONTROL_ASSESSMENT, N.PROVIDER),
        max_out=1,
    ),
    EdgeType.ASSESSED: _rule((N.PERSON, N.CONTROL_ASSESSMENT)),
    EdgeType.SUPPORTS: _rule((N.EVIDENCE, N.CONTROL_ASSESSMENT)),
    EdgeType.ABOUT: _rule(*((N.EVIDENCE, node_type) for node_type in NodeType)),
    EdgeType.COLLECTED_FROM: _rule((N.EVIDENCE, N.AWS_RESOURCE)),
    EdgeType.IMPLEMENTS: _rule((N.POLICY, N.CONTROL)),
    EdgeType.OBSERVED: _rule((N.DISCOVERY_RUN, N.AWS_RESOURCE)),
    EdgeType.AFFECTS: _rule((N.CHANGE_EVENT, N.AWS_RESOURCE)),
}
del N


def validate_edge(
    edge: Edge,
    src: Node | None,
    dst: Node | None,
    open_out_edges: Iterable[Edge] = (),
) -> None:
    """Raise `InvalidEdgeError` if `edge` may not be written.

    `src` and `dst` are the stored endpoint nodes (None if missing). `open_out_edges` are the
    source's currently open outgoing edges, used for `max_out`.
    """
    if src is None or dst is None:
        missing = edge.src if src is None else edge.dst
        raise InvalidEdgeError("missing_endpoint", f"{edge.type}: {missing!r} is not in the graph")
    if (src.id, dst.id) != (edge.src, edge.dst):
        raise InvalidEdgeError(
            "endpoint_mismatch", f"nodes passed do not match the {edge.type} edge"
        )
    if not (edge.tenant == src.tenant == dst.tenant):
        raise InvalidEdgeError("tenant_mismatch", f"{edge.type} edge crosses tenants")
    if edge.valid_to is None and (src.valid_to is not None or dst.valid_to is not None):
        ended = src.id if src.valid_to is not None else dst.id
        raise InvalidEdgeError("endpoint_ended", f"{ended!r} has ended, so no edge can stay open")

    rule = EDGE_RULES[edge.type]
    if (src.type, dst.type) not in rule.pairs:
        raise InvalidEdgeError(
            "endpoint_types", f"{edge.type} cannot connect a {src.type} to a {dst.type}"
        )

    if rule.max_out is not None:
        others = [e for e in open_out_edges if e.type == edge.type and e.key != edge.key]
        if len(others) + 1 > rule.max_out:
            raise InvalidEdgeError(
                "max_out", f"{edge.src!r} already has an open {edge.type} edge (max {rule.max_out})"
            )

    if edge.type is EdgeType.PROVIDED_BY and _origin(src) is not ModelOrigin.THIRD_PARTY:
        raise InvalidEdgeError(
            "provided_by_third_party_only", f"{src.id!r} is not a third-party model"
        )
    if edge.type is EdgeType.ASSUMES and not _is_role(dst):
        raise InvalidEdgeError("assumes_target_is_role", f"{dst.id!r} is not an IAM role")


def validate_node_change(
    new: Node,
    open_edges: Iterable[Edge] = (),
    organisation_ids: Collection[str] = (),
) -> None:
    """Raise if writing `new` would break a rule.

    Closes the bypass where a node is changed after its edges were validated, for example
    flipping a model to in-house while it still has a PROVIDED_BY edge.

    `open_edges` are the open edges touching `new`; `organisation_ids` are the Organisation
    nodes already in the tenant.
    """
    open_edges = list(open_edges)
    if isinstance(new, Model) and new.origin is ModelOrigin.IN_HOUSE:
        for edge in open_edges:
            if edge.type is EdgeType.PROVIDED_BY and edge.src == new.id:
                raise InvalidEdgeError(
                    "provided_by_third_party_only", f"{new.id!r} has a provider but is in-house"
                )
    if isinstance(new, AWSResource) and not _is_role(new):
        for edge in open_edges:
            if edge.type is EdgeType.ASSUMES and edge.dst == new.id:
                raise InvalidEdgeError(
                    "assumes_target_is_role", f"{new.id!r} is assumed by a function but is no role"
                )
    if new.type is NodeType.ORGANISATION and any(o != new.id for o in organisation_ids):
        raise InvalidNodeError(
            "organisation_per_tenant", f"tenant {new.tenant!r} already has an Organisation"
        )


def _origin(node: Node) -> ModelOrigin | None:
    return node.origin if isinstance(node, Model) else None


def _is_role(node: Node) -> bool:
    return isinstance(node, AWSResource) and node.resource_type == IAM_ROLE_RESOURCE_TYPE
