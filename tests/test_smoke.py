import sys

import verity_core


def test_package_imports():
    assert verity_core.__version__


def test_python_is_3_12():
    # Lambda runs python3.12 (docs/architecture.md section B); local dev must match.
    assert sys.version_info[:2] == (3, 12)
