"""Writes the snapshot contract: `web/generated/snapshot.schema.json` from the pydantic models,
then `web/generated/snapshot.ts` from that schema (ADR 0029, decision 12).

Run with: uv run python scripts/generate_snapshot_contract.py [--schema-only]

The direction is one way, so the frontend and the backend cannot drift: the models are the
source, the schema follows, the types follow the schema. CI runs this and fails on a difference.
The TypeScript step needs `npm ci --prefix web` first (json-schema-to-typescript, an exact
version in `web/package-lock.json`). Neither step reads the graph or AWS.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from verity_core.export.snapshot import Snapshot

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "web" / "generated"
SCHEMA = GENERATED / "snapshot.schema.json"
TYPES = GENERATED / "snapshot.ts"


def schema_text() -> str:
    """Stable text: sorted keys, two-space indent, a final newline."""
    schema = Snapshot.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Snapshot"
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_schema() -> None:
    GENERATED.mkdir(parents=True, exist_ok=True)
    SCHEMA.write_text(schema_text(), encoding="utf-8")


def write_types() -> None:
    binary = ROOT / "web" / "node_modules" / ".bin" / "json2ts"
    if not binary.exists():
        sys.exit("json2ts is missing: run `npm ci --prefix web` first")
    subprocess.run(
        [str(binary), "--input", str(SCHEMA), "--output", str(TYPES), "--no-additionalProperties"],
        check=True,
        cwd=ROOT / "web",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--schema-only", action="store_true", help="skip the TypeScript step")
    args = parser.parse_args()
    write_schema()
    if not args.schema_only:
        write_types()


if __name__ == "__main__":
    main()
