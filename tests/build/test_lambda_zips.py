"""The Lambda zips: small, deterministic and free of what a function must not carry (ADR 0023,
ADR 0025). Seven are the estate's and two are Verity's own, the crawler and the probe.

One session fixture builds twice. Needs network access to PyPI for the pydantic wheels, which is
not AWS."""

import hashlib
import re
import subprocess
import sys
import textwrap
import zipfile

from estate_support import ROOT

MB = 1024 * 1024
FORBIDDEN_TOP = {"boto3", "botocore", "networkx", "yaml", "training"}
ESTATE = (
    "support-assistant",
    "talent-screening",
    "contract-insights",
    "shadow-summariser",
    "invoice-renderer",
    "mock-bedrock",
    "mock-openai",
)
OWN = ("verity-crawler", "verity-probe")


def names(path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_there_are_nine_zips_seven_for_the_estate_and_two_of_verity_own(builds):
    script, first, _ = builds
    assert set(first) == set(script.FUNCTIONS) == {*ESTATE, *OWN}
    assert len(first) == 9
    assert set(script.ESTATE_APPS) == set(ESTATE)
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


def test_no_estate_zip_carries_what_a_function_must_not(builds):
    _, first, _ = builds
    for function in ESTATE:
        listed = names(first[function])
        assert not {n.split("/")[0] for n in listed} & FORBIDDEN_TOP, function


def test_no_zip_carries_caches_or_metadata(builds):
    _, first, _ = builds
    for function, path in first.items():
        listed = names(path)
        assert not [n for n in listed if "__pycache__" in n or ".dist-info" in n], function
        assert not {n.split("/")[0] for n in listed} & {"boto3", "botocore", "training"}, function


def test_compiled_files_are_for_linux_arm64_and_python_3_12(builds):
    _, first, _ = builds
    for function in ("support-assistant", "verity-crawler", "verity-probe"):
        compiled = [n for n in names(first[function]) if n.endswith(".so")]
        assert compiled, function
        assert all("aarch64-linux-gnu" in n and "cpython-312" in n for n in compiled), function


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
    for own in OWN:
        assert {"verity_core", "pydantic"} <= tops[own], own
        assert "verity_ai" not in tops[own], own


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
    stray = re.compile(r"(^|/)(\.DS_Store|\.lock|\.env.*|.*\.pyc|.*\.swp)$")
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
    script.vendor(tmp_path, ("pydantic",))
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


def core_of(first, function):
    return sorted(n for n in names(first[function]) if n.startswith("verity_core/"))


def import_closure(relative: str) -> list[str]:
    """The `verity_core` files a module imports, found by running it with `sys.modules`."""
    code = f"""
        import importlib.util, json, sys
        spec = importlib.util.spec_from_file_location("probe_target", {str(ROOT / relative)!r})
        spec.loader.exec_module(importlib.util.module_from_spec(spec))
        root = {str(ROOT / "core/verity_core")!r} + "/"
        print(json.dumps(sorted(
            "verity_core/" + m.__file__.removeprefix(root)
            for n, m in sys.modules.items()
            if n.split(".")[0] == "verity_core" and getattr(m, "__file__", None)
        )))
    """
    done = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, cwd=ROOT
    )
    assert done.returncode == 0, done.stderr
    import json

    return json.loads(done.stdout)


def test_the_zips_carry_only_the_verity_core_the_functions_import(builds):
    script, first, _ = builds
    for function in ("support-assistant", "contract-insights"):
        core = core_of(first, function)
        assert core == sorted(
            f"verity_core/{p.relative_to(ROOT / 'core/verity_core')}"
            for p in script.collect(ROOT / "core/verity_core", "", script.APP_CORE).values()
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


# --- the crawler and the probe (ADR 0025) --------------------------------------------------


def test_the_crawler_carries_exactly_the_44_modules_it_imports(builds):
    script, first, _ = builds
    assert len(script.CRAWLER_CORE) == 44
    assert core_of(first, "verity-crawler") == import_closure("crawler/handler.py")


def test_the_probe_carries_exactly_the_modules_it_imports(builds):
    _, first, _ = builds
    assert core_of(first, "verity-probe") == import_closure("crawler/probe.py")


def test_the_crawler_vendors_pydantic_networkx_and_yaml_at_their_locked_versions(builds):
    script, first, _ = builds
    listed = set(names(first["verity-crawler"]))
    tops = {n.split("/")[0] for n in listed}
    assert {"pydantic", "networkx", "yaml", "pydantic_core"} <= tops
    for package in ("pydantic", "networkx", "pyyaml"):
        for name in script.locked_closure(package):
            module = {"pyyaml": "yaml"}.get(name, name.replace("-", "_"))
            assert any(t in (module, f"{module}.py") for t in tops), name
    with zipfile.ZipFile(first["verity-crawler"]) as archive:
        assert f"__version__ = '{script.locked_version('networkx')}'" in archive.read(
            "networkx/__init__.py"
        ).decode() or script.locked_version("networkx") in "".join(
            archive.read(n).decode() for n in listed if n == "networkx/__init__.py"
        )
    yaml_so = [n for n in listed if n.startswith("_yaml") or "yaml" in n and n.endswith(".so")]
    assert all("aarch64-linux-gnu" in n for n in yaml_so if n.endswith(".so"))


def test_the_crawler_zip_holds_one_content_file_and_no_cli_or_fixture(builds):
    _, first, _ = builds
    listed = names(first["verity-crawler"])
    assert "rules/ai_signals.yaml" in listed
    assert not [n for n in listed if n.startswith(("content/", "fixtures/"))]
    assert not [n for n in listed if "fixtures" in n or n.endswith("estate.json")]
    assert "verity_core/cli.py" not in listed
    assert not [n for n in listed if n.startswith("verity_core/content/") and n.endswith(".yaml")]
    assert [
        n for n in listed if n.endswith(".yaml") and not n.startswith(("yaml/", "networkx/"))
    ] == ["rules/ai_signals.yaml"]


def test_the_crawler_ships_the_signals_the_repository_holds(builds):
    _, first, _ = builds
    with zipfile.ZipFile(first["verity-crawler"]) as archive:
        assert (
            archive.read("rules/ai_signals.yaml")
            == (ROOT / "content/rules/ai_signals.yaml").read_bytes()
        )


def test_the_crawler_hash_ignores_a_framework_edit_and_the_estate_zips_ignore_networkx(builds):
    script, first, _ = builds
    # Neither zip is built from `content/` beyond the signals file, so editing a framework or
    # the controls cannot change the crawler's hash (ADR 0025, decision 1).
    spec = script.FUNCTIONS["verity-crawler"]
    assert list(spec.files.values()) == ["crawler/handler.py", "content/rules/ai_signals.yaml"]
    assert spec.vendor == ("pydantic", "networkx", "pyyaml")
    assert all(script.FUNCTIONS[f].vendor in ((), ("pydantic",)) for f in ESTATE)


def test_the_crawler_and_probe_zips_stay_clear_of_the_estate_lists(builds):
    script, _, _ = builds
    assert script.APP_CORE != script.CRAWLER_CORE and script.APP_CORE != script.PROBE_CORE
    assert "graph/dynamodb/probe.py" not in script.APP_CORE
    assert "graph/dynamodb/repository.py" not in script.APP_CORE
