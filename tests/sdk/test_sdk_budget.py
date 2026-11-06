"""The model call and the telemetry write together fit in every function's timeout (ADR 0024).

These are sums of per-read timeouts, so they bound a call that stalls. They do not bound a body
that trickles in, or the cold start `_dependencies` spends inside the handler: M8 measures that.
"""

import json

from estate_support import ROOT
from verity_ai.aws import CONNECT_TIMEOUT, READ_TIMEOUT
from verity_ai.openai import TIMEOUT
from verity_core.graph.dynamodb.client import USAGE_BUDGET_SECONDS

SPARE_SECONDS = 1
FIXTURE = json.loads((ROOT / "content/fixtures/crawl/estate.json").read_text())


def test_the_model_timeout_and_the_usage_budget_leave_a_second_spare():
    assert FIXTURE["functions"]
    for function in FIXTURE["functions"]:
        assert function["Timeout"] >= TIMEOUT + USAGE_BUDGET_SECONDS + SPARE_SECONDS, function[
            "FunctionName"
        ]


def test_the_lambda_invoker_and_the_usage_budget_stay_under_every_timeout():
    worst = CONNECT_TIMEOUT + READ_TIMEOUT + USAGE_BUDGET_SECONDS
    assert all(worst < function["Timeout"] for function in FIXTURE["functions"])
