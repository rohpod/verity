"""The Lambda zips: small, deterministic and free of what a function must not carry (ADR 0023).

One session fixture builds twice. Needs network access to PyPI for the pydantic wheels, which is
not AWS."""

import hashlib
import importlib.util
import subprocess
import sys
import textwrap
import zipfile

import pytest
from estate_support import ROOT

MB = 1024 * 1024
FORBIDDEN_TOP = {"boto3", "botocore", "networkx", "yaml", "training"}


def load_build_script():
    spec = importlib.util.spec_from_file_location(
        "build_lambdas", ROOT / "scripts/build_lambdas.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def builds(tmp_path_factory):
    script = load_build_script()
    first = script.build(tmp_path_factory.mktemp("build-a"))
    second = script.build(tmp_path_factory.mktemp("build-b"))
    return script, first, second


def names(path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_there_are_seven_zips_named_after_the_deployed_functions(builds):
    script, first, _ = builds
    assert set(first) == set(script.FUNCTIONS)
    assert len(first) == 7
    assert all(path.name == f"{name}.zip" for name, path in first.items())


def test_every_zip_is_under_8_mb(builds):
    _, first, _ = builds
    assert {n: p.stat().st_size for n, p in first.items() if p.stat().st_size >= 8 * MB} == {}


def test_two_builds_give_identical_sha256(builds):
    _, first, second = builds
    assert {n: sha(p) for n, p in first.items()} == {n: sha(p) for n, p in second.items()}


def test_entries_are_sorted_with_a_fixed_timestamp_and_mode(builds):
    _, first, _ = builds
    with zipfile.ZipFile(first["support-assistant"]) as archive:
        infos = archive.infolist()
    assert [i.filename for i in infos] == sorted(i.filename for i in infos)
    assert {i.date_time for i in infos} == {(1980, 1, 1, 0, 0, 0)}
    assert {i.external_attr >> 16 for i in infos} == {0o644}


def test_app_py_is_at_the_root_of_every_zip(builds):
    _, first, _ = builds
    assert all("app.py" in names(path) for path in first.values())


def test_no_zip_carries_what_a_function_must_not(builds):
    _, first, _ = builds
    for function, path in first.items():
        listed = names(path)
        assert not {n.split("/")[0] for n in listed} & FORBIDDEN_TOP, function
        assert not [n for n in listed if "__pycache__" in n or ".dist-info" in n], function


def test_compiled_files_are_for_linux_arm64(builds):
    _, first, _ = builds
    compiled = [n for n in names(first["support-assistant"]) if n.endswith(".so")]
    assert compiled
    assert all("aarch64-linux-gnu" in n for n in compiled)


def test_the_data_files_ship_and_the_training_code_does_not(builds):
    _, first, _ = builds
    assert "articles.json" in names(first["support-assistant"])
    assert "coefficients.json" in names(first["talent-screening"])
    assert "template.txt" in names(first["invoice-renderer"])
    assert not [n for n in names(first["talent-screening"]) if "training" in n or "golden" in n]


def test_which_functions_carry_verity_ai_verity_core_and_pydantic(builds):
    _, first, _ = builds
    tops = {n: {x.split("/")[0] for x in names(p)} for n, p in first.items()}
    assert {"verity_ai", "verity_core", "pydantic"} <= tops["support-assistant"]
    assert {"verity_ai", "verity_core", "pydantic"} <= tops["contract-insights"]
    assert "verity_ai" in tops["shadow-summariser"]
    assert not {"verity_core", "pydantic"} & tops["shadow-summariser"]
    for plain in ("talent-screening", "invoice-renderer", "mock-bedrock", "mock-openai"):
        assert not {"verity_ai", "verity_core", "pydantic"} & tops[plain], plain


def test_the_vendored_pydantic_is_the_locked_version(builds):
    script, first, _ = builds
    with zipfile.ZipFile(first["support-assistant"]) as archive:
        init = archive.read("pydantic/version.py").decode()
    assert f"VERSION = '{script.locked_version('pydantic')}'" in init


def run_blocked(code: str, blocked: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    prelude = "import sys\n" + "".join(f"sys.modules[{name!r}] = None\n" for name in blocked)
    return subprocess.run(
        [sys.executable, "-c", prelude + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_the_usage_sink_imports_without_networkx_or_yaml():
    done = run_blocked("import verity_core.graph.dynamodb.usage", blocked=("networkx", "yaml"))
    assert done.returncode == 0, done.stderr


def test_the_blocking_helper_would_notice_a_missing_module():
    assert run_blocked("import networkx", blocked=("networkx",)).returncode != 0


def test_importing_verity_ai_loads_neither_verity_core_nor_pydantic():
    done = run_blocked(
        """
        import sys
        import verity_ai, verity_ai.bedrock, verity_ai.openai
        assert "verity_core" not in sys.modules and "pydantic" not in sys.modules
        """
    )
    assert done.returncode == 0, done.stderr
