"""Builds the nine Lambda zips into `.build/<function-name>.zip` (ADR 0023, ADR 0025).

Run with: uv run python scripts/build_lambdas.py [--out .build]

The zips are deterministic: `CodeSha256` feeds `config_hash`, so a zip that changed on every build
would raise a false ChangeEvent. Entries are sorted, with a fixed timestamp and mode, and no
`*.dist-info`. The zips that vendor packages also carry their bytecode, because `/var/task` is
read-only and a cold start would otherwise recompile them every time (ADR 0026). Source files
come from `git ls-files`, so an untracked file cannot ship (an uncommitted edit to a tracked file
still does: build from a clean tree before deploying).
`pydantic` and everything it depends on are vendored, each at its `uv.lock` version, for arm64.
Only the part of `verity_core` each function imports is included (ADR 0024), and the list is per
function. The seven estate zips never carry `networkx` or `yaml`. `verity-crawler` carries both,
with the 44 modules it imports and `rules/ai_signals.yaml` only (ADR 0025, decision 1).
`verity-probe` carries the few modules it needs. boto3 comes from the Lambda runtime.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
FILE_MODE = 0o644 << 16
SKIP_DIRS = {"__pycache__", "training"}
BYTECODE_TAG = "cpython-312"  # the Lambda runtime's: bytecode for any other version is ignored
# Unchecked hash pycs hold no timestamp and are never compared with the source, so the zips' fixed
# timestamps do not invalidate them. `dfile` keeps the build's paths out of them.
COMPILE = """
import json, py_compile, sys
for source, target, name in json.load(sys.stdin):
    py_compile.compile(
        source, cfile=target, dfile=name, doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
    )
"""


@dataclass(frozen=True)
class Spec:
    """What goes in one zip. `files` maps an archive name to a tracked file, for a function whose
    source is not a folder of its own `app.py`. `core` lists the `verity_core` paths (`None` for
    none), `vendor` the packages whose locked closures are installed for arm64."""

    source: str | None = None
    packages: tuple[str, ...] = ()
    core: tuple[str, ...] | None = None
    vendor: tuple[str, ...] = ()
    files: dict[str, str] = field(default_factory=dict)


# What `verity_core.graph.dynamodb.usage` imports, and nothing else. The rest needs networkx or
# yaml, and an edit to it would change two functions' hashes for no reason. A test runs the
# handlers from the built zip, so a file missing from this list fails there.
APP_CORE = (
    "__init__.py",
    "model/*.py",
    "graph/__init__.py",
    "graph/errors.py",
    "graph/planning.py",
    "graph/dynamodb/__init__.py",
    "graph/dynamodb/client.py",
    "graph/dynamodb/items.py",
    "graph/dynamodb/keys.py",
    "graph/dynamodb/table.py",
    "graph/dynamodb/usage.py",
)
# What `crawler/probe.py` imports. Found by importing it and listing `sys.modules`.
PROBE_CORE = (
    "__init__.py",
    "graph/__init__.py",
    "graph/dynamodb/__init__.py",
    "graph/dynamodb/client.py",
    "graph/dynamodb/keys.py",
    "graph/dynamodb/probe.py",
    "model/__init__.py",
    "model/base.py",
    "model/edges.py",
    "model/enums.py",
    "model/ids.py",
)
# What `crawler/handler.py` imports (44 modules, ADR 0025). Found the same way, and written out so
# that a new import fails a test instead of silently growing the zip.
CRAWLER_CORE = (
    "__init__.py",
    "assess/__init__.py",
    "assess/freshness.py",
    "content/__init__.py",
    "content/decisions.py",
    "content/loader.py",
    "content/org.py",
    "content/schema.py",
    "content/yamlio.py",
    "discovery/__init__.py",
    "discovery/aws.py",
    "discovery/boundary.py",
    "discovery/collectors.py",
    "discovery/correlate.py",
    "discovery/diff.py",
    "discovery/names.py",
    "discovery/persist.py",
    "discovery/pipeline.py",
    "discovery/relate.py",
    "discovery/signals.py",
    "discovery/usage.py",
    "graph/__init__.py",
    "graph/dynamodb/__init__.py",
    "graph/dynamodb/client.py",
    "graph/dynamodb/items.py",
    "graph/dynamodb/keys.py",
    "graph/dynamodb/repository.py",
    "graph/dynamodb/table.py",
    "graph/dynamodb/usage.py",
    "graph/errors.py",
    "graph/loader.py",
    "graph/planning.py",
    "graph/repository.py",
    "graph/traversals.py",
    "model/__init__.py",
    "model/base.py",
    "model/edges.py",
    "model/enums.py",
    "model/evidence.py",
    "model/hashing.py",
    "model/ids.py",
    "model/nodes.py",
    "model/usage.py",
    "model/validation.py",
)

FUNCTIONS = {
    "support-assistant": Spec(
        "apps/support_assistant", ("verity_ai", "verity_core"), APP_CORE, ("pydantic",)
    ),
    "talent-screening": Spec("apps/talent_screening"),
    "contract-insights": Spec(
        "apps/contract_insights", ("verity_ai", "verity_core"), APP_CORE, ("pydantic",)
    ),
    "shadow-summariser": Spec("apps/shadow_summariser", ("verity_ai",)),
    "invoice-renderer": Spec("apps/invoice_renderer"),
    "mock-bedrock": Spec("mocks/mock_bedrock"),
    "mock-openai": Spec("mocks/mock_openai"),
    "verity-crawler": Spec(
        packages=("verity_core",),
        core=CRAWLER_CORE,
        vendor=("pydantic", "networkx", "pyyaml"),
        files={
            "app.py": "crawler/handler.py",
            "rules/ai_signals.yaml": "content/rules/ai_signals.yaml",
        },
    ),
    "verity-probe": Spec(
        packages=("verity_core",),
        core=PROBE_CORE,
        vendor=("pydantic",),
        files={"app.py": "crawler/probe.py"},
    ),
}
ESTATE_APPS = tuple(n for n, spec in FUNCTIONS.items() if spec.source)
PACKAGE_SOURCES = {
    "verity_ai": ROOT / "sdk" / "verity_ai",
    "verity_core": ROOT / "core" / "verity_core",
}


def _lock() -> dict[str, dict]:
    return {p["name"]: p for p in tomllib.loads((ROOT / "uv.lock").read_text())["package"]}


def locked_version(package: str) -> str:
    return _lock()[package]["version"]


def locked_closure(package: str) -> dict[str, str]:
    """`package` and everything it depends on, found by walking `dependencies` in `uv.lock`."""
    lock = _lock()
    found: dict[str, str] = {}
    pending = [package]
    while pending:
        name = pending.pop()
        if name not in found:
            found[name] = lock[name]["version"]
            pending += [d["name"] for d in lock[name].get("dependencies", [])]
    return dict(sorted(found.items()))


def vendor(target: Path, packages: tuple[str, ...] = ("pydantic",)) -> None:
    """Linux arm64 wheels of the packages and what they depend on, each at its locked version."""
    closure = {n: v for package in packages for n, v in locked_closure(package).items()}
    subprocess.run(
        [
            "uv", "pip", "install",
            "--python-platform", "aarch64-manylinux2014",
            "--python-version", "3.12",
            "--only-binary", ":all:",
            "--no-deps",
            "--target", str(target),
            *(f"{name}=={version}" for name, version in sorted(closure.items())),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip


def tracked(root: Path, pathspecs: tuple[str, ...] = (".",)) -> list[Path]:
    """Files git tracks under `root`. An untracked file, such as `.DS_Store` or `.env`, is not
    listed, whatever is in the directory."""
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", *pathspecs],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [root / name for name in sorted(listed.split("\0")) if name]


def collect(root: Path, prefix: str = "", pathspecs: tuple[str, ...] = (".",)) -> dict[str, Path]:
    """Tracked files under `root`, keyed by archive name, without caches or training. With
    `pathspecs`, only the files they match."""
    found = {}
    for path in tracked(root, pathspecs):
        parts = path.relative_to(root).parts
        if not path.is_file() or SKIP_DIRS & set(parts) or path.name == ".lock":
            continue
        found[prefix + "/".join(parts)] = path
    return found


def vendored_files(vendored: Path) -> dict[str, Path]:
    """The installed wheels, without caches, console scripts, uv's `.lock`, `*.dist-info` or the
    packages' own `tests`, which nothing imports."""
    found = {}
    for path in sorted(vendored.rglob("*")):
        parts = path.relative_to(vendored).parts
        if path.is_dir() or parts[0] == "bin" or "__pycache__" in parts or path.name == ".lock":
            continue
        if "tests" in parts or any(p.endswith(".dist-info") for p in parts):
            continue
        found["/".join(parts)] = path
    return found


def write_zip(target: Path, entries: dict[str, Path]) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = FILE_MODE
            info.create_system = 3
            archive.writestr(info, entries[name].read_bytes(), compresslevel=9)


def bytecode_for(entries: dict[str, Path], target: Path) -> dict[str, Path]:
    """The `.pyc` of every `.py` in `entries`, keyed by archive name. One fresh process with a fixed
    seed and order, because marshal's output depends on the state of the process compiling."""
    if sys.implementation.cache_tag != BYTECODE_TAG:
        raise SystemExit(f"build with {BYTECODE_TAG}, not {sys.implementation.cache_tag}")
    found = {}
    jobs = []
    for name in sorted(n for n in entries if n.endswith(".py")):
        source = Path(name)
        archive_name = f"{source.parent / '__pycache__' / source.stem}.{BYTECODE_TAG}.pyc"
        found[archive_name] = target / archive_name
        jobs.append((str(entries[name]), str(found[archive_name]), name))
    subprocess.run(
        [sys.executable, "-c", COMPILE],
        input=json.dumps(jobs),
        env={**os.environ, "PYTHONHASHSEED": "0"},
        check=True,
        capture_output=True,
        text=True,
    )
    return found


def entries_for(spec: Spec, vendored: dict[tuple[str, ...], Path]) -> dict[str, Path]:
    entries = collect(ROOT / spec.source) if spec.source else {}
    for archive_name, relative in spec.files.items():
        path = ROOT / relative
        (found,) = collect(path.parent, pathspecs=(path.name,)).values()  # tracked, or it fails
        entries[archive_name] = found
    for package in spec.packages:
        pathspecs = (spec.core or (".",)) if package == "verity_core" else (".",)
        entries |= collect(PACKAGE_SOURCES[package], f"{package}/", pathspecs)
    if spec.vendor:
        entries |= vendored_files(vendored[spec.vendor])
    return entries


def build(out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    zips = {}
    with tempfile.TemporaryDirectory() as scratch:
        vendored = {}
        for index, packages in enumerate(sorted({spec.vendor for spec in FUNCTIONS.values()})):
            if packages:
                vendored[packages] = Path(scratch) / str(index)
                vendor(vendored[packages], packages)
        for name, spec in FUNCTIONS.items():
            zips[name] = out / f"{name}.zip"
            entries = entries_for(spec, vendored)
            if spec.vendor:
                entries |= bytecode_for(entries, Path(scratch) / f"bytecode-{name}")
            write_zip(zips[name], entries)
    return zips


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / ".build")
    args = parser.parse_args()
    for name, path in build(args.out).items():
        print(f"{name}: {path.stat().st_size / 1024:.0f} KB", file=sys.stderr)


if __name__ == "__main__":
    main()
