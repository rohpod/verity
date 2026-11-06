"""The manifests M8 publishes equal the fixture's, and the crawler accepts them (ADR 0025)."""

import json
from pathlib import Path

import pytest
from verity_core.discovery.boundary import clean_manifest

CONTENT = Path(__file__).parents[2] / "content"
MANIFESTS = CONTENT / "manifests"
FIXTURE = json.loads((CONTENT / "fixtures" / "crawl" / "estate.json").read_text())
PREFIX = "/verity/manifests/"


def files() -> list[Path]:
    return sorted(MANIFESTS.glob("*.yaml"))


def test_there_is_one_file_for_each_manifest_in_the_fixture():
    assert [p.name for p in files()] == sorted(
        m["Name"].removeprefix(PREFIX) for m in FIXTURE["manifests"]
    )


@pytest.mark.parametrize("raw", FIXTURE["manifests"], ids=lambda m: m["Name"])
def test_each_file_has_the_value_the_fixture_has(raw):
    path = MANIFESTS / raw["Name"].removeprefix(PREFIX)
    assert path.read_text() == raw["Value"]


@pytest.mark.parametrize("path", files(), ids=lambda p: p.name)
def test_the_crawlers_boundary_accepts_each_file(path):
    parsed = clean_manifest({"Name": PREFIX + path.name, "Value": path.read_text()})
    assert parsed is not None
    assert parsed.functions == (path.stem,)
    assert parsed.system == f"sys:{path.stem}"
