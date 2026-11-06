"""The built zips' handlers, run for real against a local fake (ADR 0024, decision 8).

The end-of-milestone review found cases the fakes in `tests/apps` could not: botocore never ran,
so its retries, its logging and a redirect were never exercised. Here each zip is extracted and
its handler runs in a subprocess with the real `botocore` and `urllib`, against a fake of
DynamoDB, Lambda and the Function URL on 127.0.0.1.

NOTHING HERE REACHES AWS: the environment is built from scratch (nothing is inherited), the
credentials are fake, and every endpoint is a local URL. `local_env` refuses to run otherwise.
The mocks' real handlers answer, so the replies are the SIMULATED ones.
"""

import json
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from estate_support import load_app

CONTENT_CANARY = "VERITY-CONTENT-CANARY-7f3a"
TOKEN_CANARY = "VERITY-TOKEN-CANARY-91c2"
THROTTLE = "com.amazonaws.dynamodb.v20120810#ProvisionedThroughputExceededException"
SUPPORT_PK = "T#kestrel#U#sys:support-assistant"
CONTRACT_PK = "T#kestrel#U#sys:contract-insights"
# Imported from the zip or from the zip's vendored wheels. Anything else means the zip was
# missing a file and the repository's copy answered instead.
OURS = {"verity_core", "verity_ai", "pydantic", "typing_extensions", "annotated_types"}

bedrock = load_app("mocks/mock_bedrock")
openai = load_app("mocks/mock_openai")

CHILD = r"""
import json, logging, sys, time

work, event, options = sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3])
sys.path.insert(0, work)
sys.modules["networkx"] = None  # a function must not need either (ADR 0023, decision 13)
sys.modules["yaml"] = None
root = logging.getLogger()
root.addHandler(logging.StreamHandler(sys.stderr))  # what the Lambda runtime installs
if options["root_debug"]:
    root.setLevel(logging.DEBUG)  # what AWS_LAMBDA_LOG_LEVEL=DEBUG does
import app

if options["unquiet"]:  # the control: undo the fix, to prove this run could see a leak
    import verity_ai.aws

    verity_ai.aws._quiet = lambda: None
    logging.getLogger("botocore").setLevel(logging.DEBUG)
started = time.monotonic()
try:
    result = {"ok": app.handler(event, None)}
except BaseException as error:
    status = getattr(error, "status", "-")
    result = {"error": type(error).__name__, "message": str(error), "status": status}
result["seconds"] = round(time.monotonic() - started, 2)
result["foreign"] = sorted(
    name for name, module in sys.modules.items()
    if name.split(".")[0] in options["ours"]
    and getattr(module, "__file__", None)
    and not module.__file__.startswith(work)
)
print(json.dumps(result, default=str))
"""


@dataclass
class Fake:
    """A local DynamoDB, Lambda and Function URL. State is reset between runs."""

    server: ThreadingHTTPServer
    throttle: bool = False
    redirect_to: str | None = None
    puts: list = field(default_factory=list)
    put_attempts: int = 0
    url_requests: list = field(default_factory=list)
    other_hits: list = field(default_factory=list)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def reset(self):
        self.throttle, self.redirect_to = False, None
        self.puts, self.put_attempts, self.url_requests, self.other_hits = [], 0, [], []


def handler_for(fake: "Fake", *, other: bool):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, content_type="application/json", headers=None):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.route(b"")

        def do_POST(self):
            self.route(self.rfile.read(int(self.headers.get("Content-Length", 0))))

        def route(self, body: bytes):
            if other:  # the second host a redirect points at: it must never be asked
                fake.other_hits.append({"path": self.path, "headers": dict(self.headers)})
                return self.reply(200, {})
            target = self.headers.get("X-Amz-Target", "")
            if target.endswith("PutItem"):
                fake.put_attempts += 1
                if fake.throttle:
                    error = {"__type": THROTTLE, "message": "throttled"}
                    return self.reply(400, error, "application/x-amz-json-1.0")
                fake.puts.append(json.loads(body))
                return self.reply(200, {}, "application/x-amz-json-1.0")
            if self.path == "/2015-03-31/functions/mock-bedrock/invocations":
                return self.reply(200, bedrock.handler(json.loads(body), None))
            if self.path == "/v1/chat/completions":
                fake.url_requests.append(dict(self.headers))
                if fake.redirect_to:
                    return self.reply(302, b"", headers={"Location": fake.redirect_to})
                event = {
                    "requestContext": {"http": {"method": "POST", "path": self.path}},
                    "body": body.decode(),
                    "isBase64Encoded": False,
                }
                response = openai.handler(event, None)
                return self.reply(response["statusCode"], response["body"].encode())
            self.reply(404, {})

    return Handler


@pytest.fixture(scope="module")
def fake():
    state = Fake(server=None)  # type: ignore[arg-type]
    state.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(state, other=False))
    other = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(state, other=True))
    state.other_port = other.server_port  # type: ignore[attr-defined]
    for server in (state.server, other):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    yield state
    for server in (state.server, other):
        server.shutdown()
        server.server_close()


@pytest.fixture
def clean_fake(fake):
    fake.reset()
    return fake


def local_env(fake: Fake, extra: dict) -> dict:
    """Built from nothing, so no real credential or setting can be inherited."""
    env = {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": TOKEN_CANARY,
        "AWS_REGION": "eu-north-1",
        "AWS_DEFAULT_REGION": "eu-north-1",
        "AWS_ENDPOINT_URL_DYNAMODB": fake.endpoint,
        "AWS_ENDPOINT_URL_LAMBDA": fake.endpoint,
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": "/nonexistent/config",
        "AWS_SHARED_CREDENTIALS_FILE": "/nonexistent/credentials",
        **extra,
    }
    for key in ("AWS_ENDPOINT_URL_DYNAMODB", "AWS_ENDPOINT_URL_LAMBDA"):
        assert env[key].startswith("http://127.0.0.1:"), "refusing to run against a real endpoint"
    assert env["AWS_ACCESS_KEY_ID"] == "testing" and env["AWS_SECRET_ACCESS_KEY"] == "testing"
    assert not {"AWS_PROFILE", "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE"} & set(env)
    return env


@dataclass
class Run:
    output: dict
    stderr: str
    wall: float


@pytest.fixture(scope="module")
def run_zip(builds, fake, tmp_path_factory):
    _, zips, _ = builds
    extracted = {}

    def extract(function: str):
        if function not in extracted:
            target = tmp_path_factory.mktemp(f"run-{function}")
            with zipfile.ZipFile(zips[function]) as archive:
                archive.extractall(target)
            # The zip's arm64 Linux .so cannot load here, so the host's pydantic_core is used.
            shutil.rmtree(target / "pydantic_core", ignore_errors=True)
            extracted[function] = target
        return extracted[function]

    def run(function, event, env, *, root_debug=False, unquiet=False, timeout=60) -> Run:
        work = extract(function)
        options = {"root_debug": root_debug, "unquiet": unquiet, "ours": sorted(OURS)}
        started = time.monotonic()
        done = subprocess.run(
            [sys.executable, "-I", "-c", CHILD, str(work), json.dumps(event), json.dumps(options)],
            env=local_env(fake, env),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work,
        )
        wall = time.monotonic() - started
        lines = done.stdout.strip().splitlines()
        assert lines, done.stderr[-2000:]
        return Run(json.loads(lines[-1]), done.stderr, wall)

    return run


def support_env(fake, **extra):
    return {
        "MODEL_ADAPTER": "mock-bedrock",
        "HELP_ARTICLES_FILE": "articles.json",
        "USAGE_TABLE": "verity-graph",
        "LOG_LEVEL": "INFO",
        **extra,
    }


def url_env(fake, **extra):
    return {"OPENAI_BASE_URL": f"http://localhost:{fake.server.server_port}/v1", **extra}


def contract_env(fake, **extra):
    return url_env(fake, **{"USAGE_TABLE": "verity-graph", "LOG_LEVEL": "INFO", **extra})


SUPPORT_EVENT = {"message": f"{CONTENT_CANARY} how do I reset my password"}
CONTRACT_EVENT = {"contract_text": f"{CONTENT_CANARY} the parties agree"}
APPLICANT = {
    "applicant_ref": "A1",
    "years_experience": 3,
    "skills_match": 0.5,
    "assessment_score": 70,
    "certifications": 1,
    "relevant_projects": 2,
}
ESTATE = {
    # function: (event, env builder, usage partitions expected)
    "support-assistant": (SUPPORT_EVENT, support_env, [SUPPORT_PK]),
    "contract-insights": (CONTRACT_EVENT, contract_env, [CONTRACT_PK]),
    "shadow-summariser": ({"text": "hello there"}, url_env, []),
    "talent-screening": (
        {"applicants": [APPLICANT]},
        lambda fake: {"COEFFICIENTS_FILE": "coefficients.json", "LOG_LEVEL": "INFO"},
        [],
    ),
    "invoice-renderer": (
        {
            "invoice_number": "INV-1",
            "customer": "Fictional Ltd",
            "lines": [{"description": "x", "quantity": 1, "unit_price": "2.50"}],
        },
        lambda fake: {"INVOICE_TEMPLATE": "template.txt"},
        [],
    ),
}


def test_every_app_handler_returns_from_its_zip_and_exactly_two_usage_items_land(
    clean_fake, run_zip
):
    measured = {}
    landed = []
    for function, (event, env_for, expected) in ESTATE.items():
        before = len(clean_fake.puts)
        result = run_zip(function, event, env_for(clean_fake))
        assert "ok" in result.output, (function, result.output, result.stderr[-500:])
        assert result.output["foreign"] == [], (function, "imported outside its zip")
        new = clean_fake.puts[before:]
        assert [p["Item"]["PK"]["S"] for p in new] == expected, function
        landed += new
        measured[function] = f"{result.output['seconds']}s, {len(new)} usage item(s)"
    assert len(landed) == 2
    assert {p["Item"]["PK"]["S"] for p in landed} == {SUPPORT_PK, CONTRACT_PK}
    assert all(p["Item"]["SK"]["S"].startswith("U#") for p in landed)
    assert {p["TableName"] for p in landed} == {"verity-graph"}
    print("\nmeasured, handlers from zips:", json.dumps(measured))


def test_the_replies_are_the_simulated_ones(clean_fake, run_zip):
    support = run_zip("support-assistant", SUPPORT_EVENT, support_env(clean_fake)).output["ok"]
    assert support["simulated"] is True and support["reply"].startswith("[SIMULATED]")
    contract = run_zip("contract-insights", CONTRACT_EVENT, contract_env(clean_fake)).output["ok"]
    assert contract["simulated"] is True and contract["summary"].startswith("[SIMULATED]")
    event, env_for, _ = ESTATE["talent-screening"]
    talent = run_zip("talent-screening", event, env_for(clean_fake)).output["ok"]
    assert talent["ranking"][0]["outside_training_range"] == []


def test_a_function_url_call_is_signed_with_the_session_token(clean_fake, run_zip):
    run_zip("shadow-summariser", {"text": "hello"}, url_env(clean_fake))
    (headers,) = clean_fake.url_requests
    lowered = {name.lower(): value for name, value in headers.items()}
    assert lowered["authorization"].startswith("AWS4-HMAC-SHA256 Credential=testing/")
    assert lowered["x-amz-security-token"] == TOKEN_CANARY


@pytest.mark.parametrize(
    ("function", "event", "env_for"),
    [
        ("support-assistant", SUPPORT_EVENT, support_env),
        ("contract-insights", CONTRACT_EVENT, contract_env),
    ],
)
def test_debug_logging_leaks_neither_the_content_nor_the_session_token(
    clean_fake, run_zip, function, event, env_for
):
    result = run_zip(function, event, env_for(clean_fake, LOG_LEVEL="DEBUG"), root_debug=True)
    assert "ok" in result.output, result.stderr[-500:]
    assert CONTENT_CANARY not in result.stderr
    assert TOKEN_CANARY not in result.stderr
    assert result.stderr == ""  # not even botocore's client set-up lines
    print(f"\nmeasured, DEBUG {function}: {len(result.stderr)} bytes of stderr, no canary")


@pytest.mark.parametrize(
    ("function", "event", "env_for"),
    [
        ("support-assistant", SUPPORT_EVENT, support_env),
        ("contract-insights", CONTRACT_EVENT, contract_env),
    ],
)
def test_the_control_run_would_have_seen_a_leak(clean_fake, run_zip, function, event, env_for):
    """Undoing the fix makes botocore log the canaries, so the check above can fail."""
    result = run_zip(
        function, event, env_for(clean_fake, LOG_LEVEL="DEBUG"), root_debug=True, unquiet=True
    )
    assert TOKEN_CANARY in result.stderr, "the fake and the logging setup cannot show a leak"


def test_a_throttled_usage_write_does_not_hold_or_fail_the_call(clean_fake, run_zip):
    clean_fake.throttle = True
    result = run_zip("support-assistant", SUPPORT_EVENT, support_env(clean_fake))
    assert "ok" in result.output, result.output
    assert result.output["seconds"] < 5
    assert clean_fake.put_attempts == 2
    assert "usage_write_failed ProvisionedThroughputExceededException" in result.stderr
    assert CONTENT_CANARY not in result.stderr
    assert clean_fake.puts == []
    print(
        f"\nmeasured, throttled DynamoDB: handler {result.output['seconds']}s, "
        f"process {result.wall:.1f}s, {clean_fake.put_attempts} attempts"
    )


def test_a_redirect_from_the_function_url_is_refused_and_the_second_host_is_never_asked(
    clean_fake, run_zip
):
    clean_fake.redirect_to = f"http://127.0.0.1:{clean_fake.other_port}/stolen"
    result = run_zip("shadow-summariser", {"text": "hello"}, url_env(clean_fake))
    assert result.output["error"] == "AdapterError" and result.output["status"] == 302
    assert len(clean_fake.url_requests) == 1
    assert clean_fake.other_hits == []
    print(
        f"\nmeasured, redirect: {result.output['error']} status {result.output['status']}, "
        f"second host requests: {len(clean_fake.other_hits)}"
    )
