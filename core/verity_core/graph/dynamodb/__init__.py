"""`DynamoDBRepository` and its storage format (ADR 0003, ADR 0013).

`keys`, `items` and `table` are pure and import no AWS library. Only this package may import
boto3, and `tests/graph/test_boto3_boundary.py` enforces that.
"""
