"""Deterministic, typed IDs (docs/architecture.md section E, ADR 0012).

An ID is `<prefix>:<parts>`. Re-crawls produce the same IDs, which is what makes
upserts idempotent. IDs end up inside `#`-delimited DynamoDB keys, so they use a
restricted charset and can never contain `#`.
"""

import re

from verity_core.model.enums import NodeType

PREFIXES: dict[NodeType, str] = {
    NodeType.ORGANISATION: "org",
    NodeType.DEPARTMENT: "dept",
    NodeType.PERSON: "person",
    NodeType.AI_SYSTEM: "sys",
    NodeType.CANDIDATE: "cand",
    NodeType.AWS_RESOURCE: "res",
    NodeType.MODEL: "model",
    NodeType.PROVIDER: "prov",
    NodeType.DATASET: "ds",
    NodeType.RISK: "risk",
    NodeType.CONTROL: "ctl",
    NodeType.CONTROL_ASSESSMENT: "ca",
    NodeType.REQUIREMENT: "req",
    NodeType.FRAMEWORK: "fw",
    NodeType.EVIDENCE: "ev",
    NodeType.POLICY: "pol",
    NodeType.DISCOVERY_RUN: "run",
    NodeType.CHANGE_EVENT: "chg",
}

_TYPE_BY_PREFIX = {prefix: node_type for node_type, prefix in PREFIXES.items()}

# Whole IDs may contain ':' (the separator). Single parts may not, or an ID would be
# ambiguous to read back.
_CA_SCOPES = {NodeType.AI_SYSTEM, NodeType.ORGANISATION, NodeType.PROVIDER}

_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_PART_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def make_id(node_type: NodeType, *parts: str) -> str:
    if not parts:
        raise ValueError(f"{node_type} ID needs at least one part")
    for part in parts:
        if not _PART_RE.fullmatch(part):
            raise ValueError(
                f"invalid ID part {part!r}: use only letters, digits, '.', '_' and '-'"
            )
    return ":".join([PREFIXES[node_type], *parts])


def node_type_of(node_id: str) -> NodeType:
    """Return the node type an ID belongs to, or raise ValueError."""
    if not _ID_RE.fullmatch(node_id):
        raise ValueError(f"invalid ID {node_id!r}: use only letters, digits, '.', '_', ':' and '-'")
    prefix, sep, rest = node_id.partition(":")
    if not sep or not rest or prefix not in _TYPE_BY_PREFIX:
        raise ValueError(f"invalid ID {node_id!r}: unknown or missing prefix")
    return _TYPE_BY_PREFIX[prefix]


def check_id(node_id: str, expected: NodeType) -> str:
    """Validate an ID for a node class, returning it unchanged."""
    actual = node_type_of(node_id)
    if actual is not expected:
        raise ValueError(f"ID {node_id!r} is a {actual} ID, expected {expected}")
    return node_id


def organisation_id(slug: str) -> str:
    return make_id(NodeType.ORGANISATION, slug)


def department_id(slug: str) -> str:
    return make_id(NodeType.DEPARTMENT, slug)


def person_id(slug: str) -> str:
    return make_id(NodeType.PERSON, slug)


def system_id(slug: str) -> str:
    return make_id(NodeType.AI_SYSTEM, slug)


def candidate_id(slug: str) -> str:
    return make_id(NodeType.CANDIDATE, slug)


def resource_id(kind: str, region: str, name: str) -> str:
    """`res:lambda:eu-north-1:talent-screening`. Use region `global` for IAM."""
    return make_id(NodeType.AWS_RESOURCE, kind, region, name)


def model_id(slug: str) -> str:
    return make_id(NodeType.MODEL, slug)


def provider_id(slug: str) -> str:
    return make_id(NodeType.PROVIDER, slug)


def dataset_id(slug: str) -> str:
    return make_id(NodeType.DATASET, slug)


def risk_id(slug: str) -> str:
    return make_id(NodeType.RISK, slug)


def control_id(code: str) -> str:
    """`ctl:VC-014`."""
    return make_id(NodeType.CONTROL, code)


def framework_id(slug: str) -> str:
    return make_id(NodeType.FRAMEWORK, slug)


def requirement_id(framework: str, ref: str) -> str:
    """`req:euaia:art50-1`, `req:iso42001:A.6.2.4`. `framework` is the framework slug."""
    return make_id(NodeType.REQUIREMENT, framework, ref)


def policy_id(slug: str) -> str:
    return make_id(NodeType.POLICY, slug)


def ca_id(control: str, scope: str) -> str:
    """One ControlAssessment per control x scope: `ca:VC-014:sys:talent-screening`.

    Takes full IDs. Re-assessments update this node, and its history lives in `H#`.
    """
    check_id(control, NodeType.CONTROL)
    if node_type_of(scope) not in _CA_SCOPES:
        raise ValueError(f"{scope!r} cannot scope a ControlAssessment")
    return f"{PREFIXES[NodeType.CONTROL_ASSESSMENT]}:{control.partition(':')[2]}:{scope}"
