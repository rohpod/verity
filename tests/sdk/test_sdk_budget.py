"""The model call and the telemetry write together fit in every function's timeout (ADR 0024)."""

import json

from estate_support import ROOT
from verity_ai.openai import TIMEOUT
from verity_core.graph.dynamodb.client import USAGE_BUDGET_SECONDS

SPARE_SECONDS = 1


def test_the_model_timeout_and_the_usage_budget_leave_a_second_spare():
    fixture = json.loads((ROOT / "content/fixtures/crawl/estate.json").read_text())
    assert fixture["functions"]
    for function in fixture["functions"]:
        assert function["Timeout"] >= TIMEOUT + USAGE_BUDGET_SECONDS + SPARE_SECONDS, function[
            "FunctionName"
        ]
