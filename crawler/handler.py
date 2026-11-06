"""The Verity crawler as a Lambda function (ADR 0025, decisions 1 and 2).

Runs one full crawl of the account with the function's own role and writes the result to the graph
through `DynamoDBRepository`. It never assesses: that stays an operator command. The return value
holds counts only, never an ARN, a function name or an account ID (D1), so the caller can print it.

Environment: `GRAPH_TABLE` (the table's name), `TENANT`, `SIGNALS_FILE` (a path inside the
package, such as `rules/ai_signals.yaml`) and optionally `LOG_LEVEL`.
"""

import logging
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from verity_core.content.loader import Content, load_signals
from verity_core.discovery.aws import AwsClients, AwsCollector
from verity_core.discovery.pipeline import CrawlReport, crawl
from verity_core.graph.dynamodb.repository import DynamoDBRepository

logger = logging.getLogger("verity_crawler")


def _now() -> datetime:
    return datetime.now(UTC)


def summarise(report: CrawlReport) -> dict:
    """Counts only. A function's name is a resource name, so it stays out (ADR 0025, decision 2)."""
    return {
        "written": dict(sorted(report.written.items())),
        "functions": len(report.functions),
        "candidates": len(report.candidates),
        "likelihood": dict(
            sorted(Counter(found.value for _, found, _ in report.functions).items())
        ),
        "changes": len(report.changes),
        "manifests_invalid": report.manifests_invalid,
        "summary": dict(sorted(report.summary.items())),
    }


def handler(event, context):
    logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    tenant = os.environ["TENANT"]
    signals = load_signals(Path(__file__).parent / os.environ["SIGNALS_FILE"])
    repo = DynamoDBRepository(tenant, _now, table_name=os.environ["GRAPH_TABLE"])
    collector = AwsCollector(
        AwsClients.create(),
        clock=_now,
        trail_event_sources=list(signals.trail_event_sources),
        trail_lookback_days=signals.trail_lookback_days,
    )
    report = crawl(repo, Content(tenant=tenant, signals=signals), collector, _now)
    result = summarise(report)
    written = sum(result["written"].values())
    logger.info("crawl finished: %s functions, %s written", result["functions"], written)
    return result
