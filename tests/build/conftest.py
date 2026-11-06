"""One build of the Lambda zips, shared by the zip tests and the handler tests."""

import importlib.util

import pytest
from estate_support import ROOT


def load_build_script():
    spec = importlib.util.spec_from_file_location(
        "build_lambdas", ROOT / "scripts/build_lambdas.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def builds(tmp_path_factory):
    """Builds twice, so a test can compare. Needs network access to PyPI (not AWS)."""
    script = load_build_script()
    first = script.build(tmp_path_factory.mktemp("build-a"))
    second = script.build(tmp_path_factory.mktemp("build-b"))
    return script, first, second
