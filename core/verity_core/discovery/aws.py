"""Reads the estate from AWS. M6 builds and tests this path with `moto` and stubs only; nothing
calls AWS until M8 (ADR 0021, decision 17). The only file outside `graph/dynamodb/` that may
use boto3: it lists resources and is not graph access.

Exactly these operations are called, and `lambda:GetFunction` never is, because it would allow
code download (architecture section D):

    lambda:ListFunctions  tag:GetResources  iam:ListRoles  iam:ListRolePolicies
    iam:GetRolePolicy  iam:ListAttachedRolePolicies  iam:GetPolicy  iam:GetPolicyVersion
    dynamodb:ListTables  ssm:GetParametersByPath  cloudtrail:LookupEvents

Every item is cleaned inside the page loop, so a raw function never leaves it.

`invoke_crawler` is the one call the operator's machine makes: it runs the deployed
`verity-crawler` (ADR 0025, decision 2), whose role makes the calls above.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from verity_core.discovery.boundary import (
    CollectedFunction,
    CollectedRole,
    CollectedTable,
    TrailEvent,
    clean_function,
    clean_manifest,
    clean_role,
    clean_table,
    clean_tags,
    clean_trail_event,
    own_account,
)
from verity_core.discovery.collectors import REGION, Collected
from verity_core.model.enums import Source

CRAWLER_FUNCTION = "verity-crawler"
CRAWLER_TIMEOUT_SECONDS = 300  # the function's own limit; the client waits a little longer
MANIFEST_PATH = "/verity/manifests"
SERVICE_ROLE_PATH = "/aws-service-role/"  # roles AWS owns: not part of the estate
QUIET_LOGGERS = ("botocore", "boto3", "urllib3")
TAGGED_TYPES = ["lambda:function", "dynamodb:table"]


@dataclass(frozen=True)
class AwsClients:
    """One boto3 client per service, injected so tests pass moto clients or stubs."""

    lambda_: Any
    tagging: Any
    iam: Any
    dynamodb: Any
    ssm: Any
    cloudtrail: Any

    @classmethod
    def create(cls, region: str = REGION) -> "AwsClients":
        import boto3

        # Each service name is a constant, so a test can prove none is a Bedrock client (ADR 0024).
        return cls(
            lambda_=boto3.client("lambda", region_name=region),
            tagging=boto3.client("resourcegroupstaggingapi", region_name=region),
            iam=boto3.client("iam", region_name=region),
            dynamodb=boto3.client("dynamodb", region_name=region),
            ssm=boto3.client("ssm", region_name=region),
            cloudtrail=boto3.client("cloudtrail", region_name=region),
        )


class AwsCollector:
    source = Source.DISCOVERED

    def __init__(
        self,
        clients: AwsClients,
        *,
        clock: Callable[[], datetime],
        trail_event_sources: list[str],
        trail_lookback_days: int,
        region: str = REGION,
    ):
        self.clients = clients
        self._clock = clock
        self._sources = trail_event_sources
        self._lookback = timedelta(days=trail_lookback_days)
        self._region = region

    def collect(self) -> Collected:
        # botocore logs whole responses at DEBUG, and ListFunctions holds env var values (D1).
        for library in QUIET_LOGGERS:
            logging.getLogger(library).setLevel(logging.WARNING)
        manifests = self._manifests()
        roles = self._roles()  # before the tables: their ARNs take the account from a role
        return Collected(
            functions=self._functions(),
            roles=roles,
            tables=self._tables(own_account(roles)),
            manifests=tuple(m for m in manifests if m is not None),
            trail_events=self._trail_events(),
            tags_by_arn=self._tags(),
            manifests_invalid=sum(m is None for m in manifests),
        )

    def _pages(self, client: Any, operation: str, **arguments: Any):
        yield from client.get_paginator(operation).paginate(**arguments)

    def _functions(self) -> tuple[CollectedFunction, ...]:
        return tuple(
            clean_function(raw)
            for page in self._pages(self.clients.lambda_, "list_functions")
            for raw in page["Functions"]
        )

    def _tags(self) -> dict[str, dict[str, str]]:
        tags: dict[str, dict[str, str]] = {}
        for page in self._pages(
            self.clients.tagging, "get_resources", ResourceTypeFilters=TAGGED_TYPES
        ):
            tags |= clean_tags(page["ResourceTagMappingList"])
        return tags

    def _tables(self, account: str) -> tuple[CollectedTable, ...]:
        return tuple(
            clean_table(name, self._region, account)
            for page in self._pages(self.clients.dynamodb, "list_tables")
            for name in page["TableNames"]
        )

    def _manifests(self):
        return [
            clean_manifest(raw)
            for page in self._pages(
                self.clients.ssm, "get_parameters_by_path", Path=MANIFEST_PATH, Recursive=True
            )
            for raw in page["Parameters"]
        ]

    def _roles(self) -> tuple[CollectedRole, ...]:
        iam = self.clients.iam
        roles = []
        for page in self._pages(iam, "list_roles"):
            for raw in page["Roles"]:
                if raw.get("Path", "/").startswith(SERVICE_ROLE_PATH):
                    continue
                name = raw["RoleName"]
                inline = [
                    {
                        "PolicyName": policy,
                        "PolicyDocument": iam.get_role_policy(RoleName=name, PolicyName=policy)[
                            "PolicyDocument"
                        ],
                    }
                    for listing in self._pages(iam, "list_role_policies", RoleName=name)
                    for policy in listing["PolicyNames"]
                ]
                attached = [
                    self._managed(item)
                    for listing in self._pages(iam, "list_attached_role_policies", RoleName=name)
                    for item in listing["AttachedPolicies"]
                ]
                roles.append(clean_role(raw, inline, attached))
        return tuple(roles)

    def _managed(self, item: dict[str, Any]) -> dict[str, Any]:
        """A managed policy's default version, which is the one that applies."""
        iam = self.clients.iam
        arn = item["PolicyArn"]
        version = iam.get_policy(PolicyArn=arn)["Policy"]["DefaultVersionId"]
        document = iam.get_policy_version(PolicyArn=arn, VersionId=version)["PolicyVersion"]
        return {"PolicyName": item["PolicyName"], "PolicyDocument": document["Document"]}

    def _trail_events(self) -> tuple[TrailEvent, ...]:
        end = self._clock()
        events = []
        for source in self._sources:
            for page in self._pages(
                self.clients.cloudtrail,
                "lookup_events",
                LookupAttributes=[{"AttributeKey": "EventSource", "AttributeValue": source}],
                StartTime=end - self._lookback,
                EndTime=end,
            ):
                events.extend(clean_trail_event(raw) for raw in page["Events"])
        return tuple(events)


class CrawlerFailed(RuntimeError):
    """The deployed crawler ran and failed. It carries no payload: an error body can name
    resources, so only the fact is kept."""


def invoke_crawler(client: Any = None, *, region: str = REGION) -> dict[str, Any]:
    """Runs the deployed crawler once and returns its summary (counts only). One attempt and a
    read timeout above the function's 300 s: a retry would start a second writer, and ADR 0014
    allows one at a time."""
    if client is None:
        import boto3
        from botocore.config import Config

        config = Config(
            retries={"mode": "standard", "total_max_attempts": 1},
            read_timeout=CRAWLER_TIMEOUT_SECONDS + 30,
            connect_timeout=10,
        )
        client = boto3.client("lambda", region_name=region, config=config)
    response = client.invoke(FunctionName=CRAWLER_FUNCTION, InvocationType="RequestResponse")
    payload = response["Payload"].read()
    if response.get("FunctionError"):
        raise CrawlerFailed("the crawler function returned an error")
    return json.loads(payload)
