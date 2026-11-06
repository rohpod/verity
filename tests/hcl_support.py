"""Reads the OpenTofu files without running OpenTofu, so CI needs no provider or credentials."""

from pathlib import Path

import hcl2

INFRA = Path(__file__).parents[1] / "infra"
ESTATE = INFRA / "modules" / "estate"
FAKE_ACCOUNT = "000000000000"


def clean(value):
    """python-hcl2 keeps the quotes of string literals in some versions."""
    if isinstance(value, str):
        return value.strip('"')
    if isinstance(value, dict):
        return {clean(k): clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def parse(path: Path) -> dict:
    with path.open() as file:
        return clean(hcl2.load(file))


def files(root: Path = INFRA):
    for path in sorted(root.rglob("*.tf")):
        if ".terraform" not in path.parts:
            yield path


def resources(root: Path = INFRA) -> dict[str, dict]:
    found = {}
    for path in files(root):
        for block in parse(path).get("resource", []):
            for kind, named in block.items():
                found.setdefault(kind, {}).update(named)
    return found


def blocks(kind: str, root: Path = INFRA) -> dict[str, dict]:
    """`variable`, `provider`, `module` and the like, by name."""
    found = {}
    for path in files(root):
        for block in parse(path).get(kind, []):
            found.update(block)
    return found


def estate_locals() -> dict:
    found = {}
    for path in files(ESTATE):
        for block in parse(path).get("locals", []):
            found.update(block)
    return found


def with_account(value, account: str = FAKE_ACCOUNT):
    """Substitutes `${var.account_id}` throughout a value read from the estate's locals."""
    if isinstance(value, str):
        return value.replace("${var.account_id}", account)
    if isinstance(value, dict):
        return {k: with_account(v, account) for k, v in value.items()}
    if isinstance(value, list):
        return [with_account(v, account) for v in value]
    return value
