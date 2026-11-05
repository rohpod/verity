"""Only the DynamoDB repository may use boto3 (CLAUDE.md, ADR 0003, M2 validation).

The check reads every tracked Python file outside `tests/`, so a new package or Lambda is
covered without editing this test."""

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = ROOT / "core" / "verity_core" / "graph" / "dynamodb"
AWS_LIBRARIES = {"boto3", "botocore", "aioboto3", "aiobotocore"}


def source_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return [ROOT / f for f in listed if not f.startswith("tests/")]


def aws_uses(path: Path) -> list[str]:
    """Imports of an AWS library, plus string-built imports such as `import_module("boto3")`."""
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] in AWS_LIBRARIES]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in AWS_LIBRARIES:
                found.append(node.module)
        elif isinstance(node, ast.Call) and node.args:
            arg = node.args[0]
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if (
                name in {"import_module", "__import__"}
                and isinstance(arg, ast.Constant)
                and str(arg.value).split(".")[0] in AWS_LIBRARIES
            ):
                found.append(str(arg.value))
    return found


def test_the_scan_sees_the_repository_and_the_files_that_should_use_boto3():
    files = source_files()
    assert len(files) > 20
    users = {f.relative_to(ROOT).as_posix() for f in files if aws_uses(f)}
    assert "core/verity_core/graph/dynamodb/client.py" in users


def test_no_source_file_outside_the_dynamodb_package_uses_boto3():
    offenders = {
        f.relative_to(ROOT).as_posix(): aws_uses(f)
        for f in source_files()
        if ALLOWED not in f.parents and aws_uses(f)
    }
    assert offenders == {}


def test_the_detector_catches_each_way_of_reaching_boto3(tmp_path):
    cases = [
        "import boto3",
        "import botocore.exceptions",
        "from boto3.dynamodb import types",
        "from botocore.config import Config",
        "import importlib\nimportlib.import_module('boto3')",
        "__import__('botocore')",
    ]
    for i, code in enumerate(cases):
        path = tmp_path / f"case{i}.py"
        path.write_text(code)
        assert aws_uses(path), code
    clean = tmp_path / "clean.py"
    clean.write_text("import json\nfrom verity_core.graph.dynamodb import DynamoDBRepository")
    assert aws_uses(clean) == []
