"""Loads an estate app by path and wires the adapters to the real mock handlers, locally."""

import importlib.util
import json
from pathlib import Path
from urllib.parse import urlsplit

from verity_ai.errors import AdapterError

ROOT = Path(__file__).resolve().parents[1]


def load_app(relative: str):
    """Every function is one `app.py`, so the name `app` is shared: load each by path."""
    path = ROOT / relative / "app.py"
    spec = importlib.util.spec_from_file_location(f"estate_{relative.replace('/', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local_invoker(handler):
    """What `lambda_invoker` does, without Lambda: a JSON round trip, and an error on failure."""

    def invoke(event: dict) -> dict:
        try:
            return json.loads(json.dumps(handler(json.loads(json.dumps(event)), None)))
        except Exception as error:
            raise AdapterError(200) from error

    return invoke


def url_transport(handler):
    """A transport that builds a Function URL event (payload format 2.0) for the handler."""

    def transport(method, url, body, headers, timeout):
        event = {
            "version": "2.0",
            "requestContext": {"http": {"method": method, "path": urlsplit(url).path}},
            "headers": {k.lower(): v for k, v in headers.items()},
            "body": body.decode(),
            "isBase64Encoded": False,
        }
        response = handler(event, None)
        return response["statusCode"], response["body"].encode()

    return transport


def imported_modules(relative: str) -> set[str]:
    """Top-level names an `app.py` imports, anywhere in the file, including inside functions."""
    import ast

    tree = ast.parse((ROOT / relative / "app.py").read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found
