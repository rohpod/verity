"""IDs of the resources the crawler writes. Region is the single one, eu-north-1 (ADR 0011)."""

from verity_core.discovery.collectors import REGION
from verity_core.model import ids

LAMBDA = "lambda"
TABLE = "dynamodb-table"
ROLE = "iam-role"


def function_id(name: str) -> str:
    return ids.resource_id(LAMBDA, REGION, name)


def table_id(name: str) -> str:
    return ids.resource_id(TABLE, REGION, name)


def role_id(name: str) -> str:
    """IAM roles have no region, and a name may hold characters an ID part does not allow."""
    return ids.resource_id(ROLE, "global", ids.iam_role_part(name))


def role_name_of(arn: str) -> str | None:
    """`arn:aws:iam::<account>:role/service-role/name` gives `name`."""
    _, sep, path = arn.partition(":role/")
    return path.rpartition("/")[2] if sep and path else None
