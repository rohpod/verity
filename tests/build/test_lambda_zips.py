"""The Lambda zips: small, deterministic and free of what a function must not carry (ADR 0023).

One session fixture builds twice. Needs network access to PyPI for the pydantic wheels, which is
not AWS."""

import hashlib
import importlib.util
import re
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


def test_compiled_files_are_for_linux_arm64_and_python_3_12(builds):
    _, first, _ = builds
    compiled = [n for n in names(first["support-assistant"]) if n.endswith(".so")]
    assert compiled
    assert all("aarch64-linux-gnu" in n and "cpython-312" in n for n in compiled)


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


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_an_untracked_file_is_not_collected(builds, tmp_path):
    script, _, _ = builds
    git(tmp_path, "init", "-q")
    (tmp_path / "app.py").write_text("handler = None\n")
    (tmp_path / "data.json").write_text("{}")
    git(tmp_path, "add", "app.py", "data.json")
    for stray in (".DS_Store", ".env"):
        (tmp_path / stray).write_text("secret")
    (tmp_path / "notes.txt").write_text("not added")
    assert sorted(script.collect(tmp_path)) == ["app.py", "data.json"]


def test_a_tracked_file_deleted_from_disk_is_not_collected(builds, tmp_path):
    script, _, _ = builds
    git(tmp_path, "init", "-q")
    (tmp_path / "app.py").write_text("x")
    (tmp_path / "gone.py").write_text("x")
    git(tmp_path, "add", ".")
    (tmp_path / "gone.py").unlink()
    assert sorted(script.collect(tmp_path)) == ["app.py"]


def test_the_real_sources_hold_no_stray_file_in_any_zip(builds):
    _, first, _ = builds
    stray = re.compile(r"(^|/)(\.DS_Store|\.env.*|.*\.pyc|.*\.swp)$")
    assert {f: [n for n in names(p) if stray.search(n)] for f, p in first.items()} == {
        f: [] for f in first
    }


def test_the_vendored_closure_is_every_locked_dependency_of_pydantic(builds):
    script, _, _ = builds
    closure = script.locked_closure("pydantic")
    assert {"pydantic", "pydantic-core", "typing-extensions", "annotated-types"} <= set(closure)
    assert all(closure[name] == script.locked_version(name) for name in closure)


def test_every_vendored_package_is_at_its_locked_version(builds, tmp_path):
    script, first, _ = builds
    script.vendor_pydantic(tmp_path)
    installed = {}
    for metadata in tmp_path.glob("*.dist-info/METADATA"):
        fields = dict(
            line.split(": ", 1) for line in metadata.read_text().splitlines()[:10] if ": " in line
        )
        installed[fields["Name"].lower().replace("_", "-")] = fields["Version"]
    assert installed == script.locked_closure("pydantic")
    for name in script.locked_closure("pydantic"):
        module = name.replace("-", "_")
        assert any(
            n.split("/")[0] in (module, f"{module}.py") for n in names(first["support-assistant"])
        ), name


CORE_NOT_SHIPPED = ("cli.py", "assess", "discovery", "content", "rules")


def test_the_zips_carry_only_the_verity_core_the_functions_import(builds):
    script, first, _ = builds
    for function in ("support-assistant", "contract-insights"):
        core = sorted(n for n in names(first[function]) if n.startswith("verity_core/"))
        assert core == sorted(
            f"verity_core/{p.relative_to(ROOT / 'core/verity_core')}"
            for p in script.collect(
                ROOT / "core/verity_core", "", script.CORE_FILES["verity_core"]
            ).values()
        )
        for unwanted in CORE_NOT_SHIPPED:
            assert not [n for n in core if n.split("/")[1] == unwanted], (function, unwanted)
        assert "verity_core/graph/dynamodb/usage.py" in core
        assert not [n for n in core if "repository" in n or "loader" in n or "memory" in n]


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
