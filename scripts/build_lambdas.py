"""Builds the seven Lambda zips into `.build/<function-name>.zip` (ADR 0023).

Run with: uv run python scripts/build_lambdas.py [--out .build]

The zips are deterministic: `CodeSha256` feeds `config_hash`, so a zip that changed on every build
would raise a false ChangeEvent. Entries are sorted, with a fixed timestamp and mode, and no
`__pycache__` or `*.dist-info`. Source files come from `git ls-files`, so an untracked file cannot
ship (an uncommitted edit to a tracked file still does: build from a clean tree before deploying).
`pydantic` and everything it depends on are vendored, each at its `uv.lock` version, for arm64.
Only the part of `verity_core` the functions import is included (ADR 0024). boto3 comes from the
Lambda runtime. `networkx` and `yaml` are never included.
"""

import argparse
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
FILE_MODE = 0o644 << 16
SKIP_DIRS = {"__pycache__", "training"}

# function name -> (source directory, extra packages)
FUNCTIONS = {
    "support-assistant": ("apps/support_assistant", ("verity_ai", "verity_core", "pydantic")),
    "talent-screening": ("apps/talent_screening", ()),
    "contract-insights": ("apps/contract_insights", ("verity_ai", "verity_core", "pydantic")),
    "shadow-summariser": ("apps/shadow_summariser", ("verity_ai",)),
    "invoice-renderer": ("apps/invoice_renderer", ()),
    "mock-bedrock": ("mocks/mock_bedrock", ()),
    "mock-openai": ("mocks/mock_openai", ()),
}
PACKAGE_SOURCES = {
    "verity_ai": ROOT / "sdk" / "verity_ai",
    "verity_core": ROOT / "core" / "verity_core",
}
# What `verity_core.graph.dynamodb.usage` imports, and nothing else. The rest needs networkx or
# yaml, and an edit to it would change two functions' hashes for no reason. A test runs the
# handlers from the built zip, so a file missing from this list fails there.
CORE_FILES = {
    "verity_core": (
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


def vendor_pydantic(target: Path) -> None:
    """Linux arm64 wheels of pydantic and its dependencies, each at its locked version."""
    subprocess.run(
        [
            "uv", "pip", "install",
            "--python-platform", "aarch64-manylinux2014",
            "--python-version", "3.12",
            "--only-binary", ":all:",
            "--no-deps",
            "--target", str(target),
            *(f"{name}=={version}" for name, version in locked_closure("pydantic").items()),
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
    """The installed wheels, without caches, console scripts or `*.dist-info` metadata."""
    found = {}
    for path in sorted(vendored.rglob("*")):
        parts = path.relative_to(vendored).parts
        if path.is_dir() or parts[0] == "bin" or "__pycache__" in parts:
            continue
        if any(p.endswith(".dist-info") for p in parts):
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


def build(out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    zips = {}
    with tempfile.TemporaryDirectory() as scratch:
        vendored = Path(scratch)
        if any("pydantic" in extra for _, extra in FUNCTIONS.values()):
            vendor_pydantic(vendored)
        for name, (source, extra) in FUNCTIONS.items():
            entries = collect(ROOT / source)
            for package in extra:
                if package == "pydantic":
                    continue
                entries |= collect(
                    PACKAGE_SOURCES[package], f"{package}/", CORE_FILES.get(package, (".",))
                )
            if "pydantic" in extra:
                entries |= vendored_files(vendored)
            zips[name] = out / f"{name}.zip"
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
