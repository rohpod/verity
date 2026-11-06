"""Builds the seven Lambda zips into `.build/<function-name>.zip` (ADR 0023).

Run with: uv run python scripts/build_lambdas.py [--out .build]

The zips are deterministic: `CodeSha256` feeds `config_hash`, so a zip that changed on every build
would raise a false ChangeEvent. Entries are sorted, with a fixed timestamp and mode, and no
`__pycache__` or `*.dist-info`. Only `pydantic` is vendored, at the version in `uv.lock`, for
arm64. boto3 comes from the Lambda runtime. `networkx` and `yaml` are never included.
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


def locked_version(package: str) -> str:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    return next(p["version"] for p in lock["package"] if p["name"] == package)


def vendor_pydantic(target: Path) -> None:
    """Linux arm64 wheels of pydantic and its dependencies, with no tests of ours involved."""
    subprocess.run(
        [
            "uv", "pip", "install",
            "--python-platform", "aarch64-manylinux2014",
            "--python-version", "3.12",
            "--only-binary", ":all:",
            "--target", str(target),
            f"pydantic=={locked_version('pydantic')}",
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip


def collect(root: Path, prefix: str = "") -> dict[str, Path]:
    """Every file under `root`, keyed by archive name, without caches, metadata or training."""
    found = {}
    for path in root.rglob("*"):
        parts = path.relative_to(root).parts
        if path.is_dir() or SKIP_DIRS & set(parts) or path.name == ".lock":
            continue
        if any(p.endswith(".dist-info") for p in parts):
            continue
        found[prefix + "/".join(parts)] = path
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
                entries |= collect(PACKAGE_SOURCES[package], f"{package}/")
            if "pydantic" in extra:
                entries |= {k: v for k, v in collect(vendored).items() if k.split("/")[0] != "bin"}
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
