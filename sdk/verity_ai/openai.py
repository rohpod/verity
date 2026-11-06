"""`OpenAICompatible`: the chat-completions shape, sent to `mock-openai`.

SIMULATED. Nothing here calls OpenAI. It refuses any base URL that is not a Lambda Function URL
in eu-north-1 or localhost (ADR 0023, decision 8), and the request is signed by an injected
`sign` callable because the Function URL uses `AWS_IAM` auth (ADR 0009).
"""

import http.client
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from urllib.parse import urlsplit

from verity_ai.errors import AdapterError, RefusedTarget
from verity_ai.hook import UsageHook, notify

# method, url, body, headers -> headers to send
Signer = Callable[[str, str, bytes, dict], dict]
# method, url, body, headers, timeout -> status, response body
Transport = Callable[[str, str, bytes, dict, float], tuple[int, bytes]]

TIMEOUT = 5.0  # per socket read, not a total: a body that trickles in can take longer
_URL_SUFFIX = ".lambda-url.eu-north-1.on.aws"


def check_base_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    if parts.username or parts.password or parts.query or parts.fragment:
        raise RefusedTarget("the base URL has credentials, a query or a fragment")
    is_function_url = (
        parts.scheme == "https" and host.endswith(_URL_SUFFIX) and len(host) > len(_URL_SUFFIX)
    )
    is_local = parts.scheme == "http" and host == "localhost"
    if not (is_function_url or is_local):
        raise RefusedTarget("only a mock Function URL in eu-north-1 or localhost is allowed")
    if parts.path.rstrip("/") != "/v1":
        raise RefusedTarget("the base URL must end in /v1")
    return base_url.rstrip("/")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would send the signed headers to a host the guard never checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def urllib_transport(method: str, url: str, body: bytes, headers: dict, timeout: float):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _opener.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, b""  # includes a 3xx, which is not followed
    except (OSError, http.client.HTTPException):  # `getresponse` and `read` raise these bare
        raise AdapterError(None) from None


class OpenAICompatible:
    def __init__(
        self,
        base_url: str,
        *,
        sign: Signer,
        usage: UsageHook | None,
        transport: Transport = urllib_transport,
    ):
        self._base_url = check_base_url(base_url)
        self._sign = sign
        self._usage = usage
        self._transport = transport

    def chat_completions(self, *, model, messages, **params) -> dict:
        url = f"{self._base_url}/chat/completions"
        body = json.dumps({"model": model, "messages": messages, **params}).encode()
        headers = self._sign("POST", url, body, {"Content-Type": "application/json"})
        status, payload = self._transport("POST", url, body, headers, TIMEOUT)
        if status != 200:
            raise AdapterError(status)
        try:
            response = json.loads(payload)
            tokens = response["usage"]["total_tokens"]
        except (ValueError, KeyError, TypeError):
            raise AdapterError(status) from None  # the body may hold personal data
        notify(self._usage, tokens)
        return response
