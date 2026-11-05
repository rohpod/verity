"""`DynamoDBRepository` and its storage format (ADR 0003, ADR 0013).

`keys`, `items` and `table` are pure and import no AWS library. Only the repository modules
(added in later M2 PRs) import boto3, which keeps the boundary easy to check.
"""
