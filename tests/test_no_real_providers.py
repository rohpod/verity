"""Bedrock and OpenAI are mock-only (CLAUDE.md, ADR 0007, ADR 0023). A real client must not appear.

Same style as `tests/graph/test_boto3_boundary.py`: every tracked Python file is parsed, so a new
package or Lambda is covered without editing this test."""

import ast
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_LIBRARIES = {
    "openai",
    "anthropic",
    "langchain_openai",
    "langchain_anthropic",
    "litellm",
    "cohere",
    "mistralai",
    "google.generativeai",
}
PROVIDER_PACKAGES = {"openai", "anthropic"}
# Any string starting `bedrock-` or `sagemaker-` is taken for a real service name, so a service
# added next year (`bedrock-data-automation-runtime`) is caught without editing this test.
REAL_SERVICE_PREFIXES = ("bedrock-", "sagemaker-")
REAL_SERVICE_NAMES = {"bedrock"}
REAL_ENDPOINT_PARTS = ("api.openai.com", "bedrock-runtime.")
# Everything allowed to use boto3: two files and one package (tests/graph/test_boto3_boundary.py).
ADAPTER_AWS = "sdk/verity_ai/aws.py"
COLLECTOR = "core/verity_core/discovery/aws.py"
DYNAMODB_CLIENT = "core/verity_core/graph/dynamodb/client.py"
DYNAMODB_PACKAGE = ROOT / "core/verity_core/graph/dynamodb"
BOTO3_FILES = (
    ADAPTER_AWS,
    COLLECTOR,
    *sorted(p.relative_to(ROOT).as_posix() for p in DYNAMODB_PACKAGE.glob("*.py")),
)
CLIENT_FACTORIES = {"client", "resource", "create_client"}


def tracked(*, tests: bool) -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return [ROOT / f for f in listed if f.startswith("tests/") == tests]


def _library(name: str) -> bool:
    return any(name == lib or name.startswith(lib + ".") for lib in PROVIDER_LIBRARIES)


def library_imports(path: Path) -> list[str]:
    """Imports of a provider library, including string-built ones."""
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if _library(a.name)]
        elif isinstance(node, ast.ImportFrom) and node.module and _library(node.module):
            found.append(node.module)
        elif isinstance(node, ast.Call) and node.args:
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            arg = node.args[0]
            is_import = name in {"import_module", "__import__"}
            if is_import and isinstance(arg, ast.Constant) and _library(str(arg.value)):
                found.append(str(arg.value))
    return found


def is_real_service(name: str) -> bool:
    return name in REAL_SERVICE_NAMES or name.startswith(REAL_SERVICE_PREFIXES)


def real_strings(path: Path) -> list[str]:
    """Strings naming a real Bedrock or SageMaker runtime service, or a real endpoint."""
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if is_real_service(value) or any(p in value for p in REAL_ENDPOINT_PARTS):
                found.append(value)
    return found


def _client_calls(path: Path) -> list[ast.Call]:
    """`.client(`, `.resource(` and `create_client(`, on any object or called bare."""
    return [
        node
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", getattr(node.func, "id", "")) in CLIENT_FACTORIES
    ]


def _service_name(call: ast.Call) -> ast.expr | None:
    if call.args:
        return call.args[0]
    return next((k.value for k in call.keywords if k.arg == "service_name"), None)


def bedrock_clients(path: Path) -> list[str]:
    """Client or resource calls naming a Bedrock or SageMaker service."""
    found = []
    for call in _client_calls(path):
        name = _service_name(call)
        if isinstance(name, ast.Constant) and is_real_service(str(name.value)):
            found.append(str(name.value))
    return found


def dynamic_clients(path: Path) -> int:
    """`.client(...)` calls whose service name is not a constant."""
    return sum(not isinstance(_service_name(c), ast.Constant) for c in _client_calls(path))


def test_the_scan_sees_the_repository_and_the_files_that_should_be_clean():
    files = tracked(tests=False)
    assert len(files) > 40
    names = {f.relative_to(ROOT).as_posix() for f in files}
    assert ADAPTER_AWS in names
    assert "sdk/verity_ai/openai.py" in names
    assert "mocks/mock_bedrock/app.py" in names


def test_no_source_file_imports_a_provider_library():
    offenders = {f.name: library_imports(f) for f in tracked(tests=False) if library_imports(f)}
    assert offenders == {}


def test_no_source_file_names_a_real_bedrock_service_or_a_real_endpoint():
    offenders = {
        f.relative_to(ROOT).as_posix(): real_strings(f)
        for f in tracked(tests=False)
        if real_strings(f)
    }
    assert offenders == {}


def test_no_file_anywhere_creates_a_bedrock_client():
    offenders = {
        f.relative_to(ROOT).as_posix(): bedrock_clients(f)
        for f in tracked(tests=False) + tracked(tests=True)
        if bedrock_clients(f)
    }
    assert offenders == {}


def test_every_file_allowed_to_use_boto3_names_its_services_as_constants():
    assert {f: dynamic_clients(ROOT / f) for f in BOTO3_FILES} == dict.fromkeys(BOTO3_FILES, 0)


def test_the_boto3_files_do_create_clients_so_that_check_is_not_vacuous():
    assert DYNAMODB_CLIENT in BOTO3_FILES
    assert all(_client_calls(ROOT / f) for f in (ADAPTER_AWS, COLLECTOR, DYNAMODB_CLIENT))


def test_the_lock_file_holds_no_provider_package():
    packages = {p["name"] for p in tomllib.loads((ROOT / "uv.lock").read_text())["package"]}
    assert packages & PROVIDER_PACKAGES == set()


def test_the_detector_catches_each_way_of_reaching_a_real_provider(tmp_path):
    imports = [
        "import openai",
        "import anthropic.types",
        "from openai import OpenAI",
        "from google.generativeai import GenerativeModel",
        "import importlib\nimportlib.import_module('anthropic')",
        "__import__('openai')",
    ]
    for i, code in enumerate(imports):
        path = tmp_path / f"imp{i}.py"
        path.write_text(code)
        assert library_imports(path), code
    strings = [
        "x = 'bedrock'",
        "x = 'bedrock-runtime'",
        "x = 'bedrock-agent'",
        "x = 'bedrock-agent-runtime'",
        "x = 'bedrock-data-automation-runtime'",
        "x = 'sagemaker-runtime'",
        "x = 'sagemaker-featurestore-runtime'",
        "x = 'https://api.openai.com/v1'",
        "x = 'https://bedrock-runtime.eu-north-1.amazonaws.com'",
    ]
    for i, code in enumerate(strings):
        path = tmp_path / f"str{i}.py"
        path.write_text(code)
        assert real_strings(path), code
    clients = [
        "boto3.client('bedrock-runtime')",
        "session.client(service_name='bedrock-agent')",
        "boto3.client('bedrock')",
        "boto3.resource('bedrock-data-automation-runtime')",
        "boto3.resource(service_name='bedrock-runtime')",
        "session.create_client('bedrock-runtime')",
        "create_client('sagemaker-runtime')",
        "boto3.client('sagemaker-a2i-runtime')",
    ]
    for i, code in enumerate(clients):
        path = tmp_path / f"cli{i}.py"
        path.write_text(code)
        assert bedrock_clients(path), code
    dynamic = tmp_path / "dynamic.py"
    dynamic.write_text(
        "boto3.client(name)\nboto3.client(service_name=name)\n"
        "boto3.client('bed' + 'rock-runtime')\nboto3.client(f'bedrock-{x}')\n"
        "boto3.client(''.join(['bed', 'rock-runtime']))\nboto3.resource(name)\n"
        "session.create_client(name)\ncreate_client(name)"
    )
    assert dynamic_clients(dynamic) == 8


def test_the_detector_leaves_clean_code_alone(tmp_path):
    clean = tmp_path / "clean.py"
    clean.write_text(
        "import json\nboto3.client('lambda')\nboto3.resource('dynamodb')\n"
        "x = 'mock-bedrock'\ny = 'bedrock:InvokeModel'\nz = 'sagemaker:InvokeEndpoint'\n"
    )
    assert library_imports(clean) == []
    assert real_strings(clean) == []
    assert bedrock_clients(clean) == []
    assert dynamic_clients(clean) == 0
