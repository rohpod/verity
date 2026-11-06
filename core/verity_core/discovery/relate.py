"""`ASSUMES` and `CALLS` between resources (architecture section D, stage 5; ADR 0021, decision
8). Pure.

`ASSUMES` runs from a function to its role. `CALLS` comes from the resource ARNs in the role's
`Allow` statements and from nothing else: env var names cannot name a target once values are
dropped, and `Resource: "*"` makes no edge, because fanning out would invent relationships.
Wildcards inside an ARN are matched with `fnmatch` against the known ARNs.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatchcase

from verity_core.discovery.boundary import CollectedFunction, CollectedRole, CollectedTable
from verity_core.discovery.names import function_id, role_id, role_name_of, table_id


@dataclass(frozen=True)
class Relations:
    assumes: frozenset[tuple[str, str]] = frozenset()  # (function ID, role ID)
    calls: frozenset[tuple[str, str]] = frozenset()  # (function ID, table or function ID)


def role_of(function: CollectedFunction, roles: Iterable[CollectedRole]) -> CollectedRole | None:
    name = role_name_of(function.role_arn)
    return next((r for r in roles if r.name == name), None)


def relations(
    functions: Iterable[CollectedFunction],
    roles: Iterable[CollectedRole],
    tables: Iterable[CollectedTable],
) -> Relations:
    functions, roles = list(functions), list(roles)
    targets = {t.arn: table_id(t.name) for t in tables} | {
        f.arn: function_id(f.name) for f in functions
    }
    assumes, calls = set(), set()
    for function in functions:
        role = role_of(function, roles)
        if role is None:
            continue
        me = function_id(function.name)
        assumes.add((me, role_id(role.name)))
        for statement in role.statements:
            if statement.effect != "Allow" or statement.negated:
                continue
            for resource in statement.resources:
                if resource == "*":
                    continue
                calls |= {
                    (me, target_id)
                    for arn, target_id in targets.items()
                    if target_id != me and fnmatchcase(arn, resource)
                }
    return Relations(frozenset(assumes), frozenset(calls))
