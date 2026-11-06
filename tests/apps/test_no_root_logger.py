"""No app changes the root logger's level (ADR 0024, decision 2). At DEBUG the root logger
makes botocore log request bodies and the session token."""

import ast

import pytest
from estate_support import ROOT

APPS = sorted(p for pattern in ("apps/*/app.py", "mocks/*/app.py") for p in ROOT.glob(pattern))


def touches_root_logger(source: str) -> bool:
    """`logging.getLogger()` or `logging.getLogger("")` or `logging.root`, used for anything."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _is_get_logger(node.func):
            if not node.args and not node.keywords:
                return True
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in ("", None)
            ):
                return True
        if isinstance(node, ast.Attribute) and node.attr == "root" and _is_logging(node.value):
            return True
        if isinstance(node, ast.Call) and _name(node.func) in ("basicConfig",):
            return True
    return False


def _is_logging(node) -> bool:
    return isinstance(node, ast.Name) and node.id == "logging"


def _is_get_logger(node) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "getLogger" and _is_logging(node.value)


def _name(node) -> str:
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


def test_the_scan_covers_every_app_and_mock():
    assert len(APPS) == 7  # five apps and two mocks


@pytest.mark.parametrize("path", APPS, ids=lambda p: p.parent.name)
def test_no_app_touches_the_root_logger(path):
    assert not touches_root_logger(path.read_text())


@pytest.mark.parametrize(
    "source",
    [
        "import logging\nlogging.getLogger().setLevel(10)",
        "import logging\nlogging.getLogger('').setLevel(10)",
        "import logging\nlogging.root.setLevel(10)",
        "import logging\nlogging.basicConfig(level=10)",
    ],
)
def test_the_detector_catches_each_form(source):
    assert touches_root_logger(source)


def test_the_detector_leaves_named_loggers_alone():
    assert not touches_root_logger("import logging\nlogging.getLogger('verity_ai').setLevel(10)")
