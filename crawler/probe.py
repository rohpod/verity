"""`verity-probe`: proves that `support-assistant-role` cannot write outside its usage partition
(ADR 0025, decision 5). It exists only while `enable_probe = true` and is destroyed before the
first crawl, so the crawler never sees it.

It attempts two writes that carry a condition which can never be true, so no item can change
whatever IAM decides. It returns the error code of each, and nothing else. Environment:
`GRAPH_TABLE`.
"""

import os

from verity_core.graph.dynamodb.client import usage_client
from verity_core.graph.dynamodb.probe import attempt_refused_writes

TENANT = "kestrel"
SYSTEM = "sys:support-assistant"
OTHER_SYSTEM = "sys:contract-insights"


def handler(event, context):
    return attempt_refused_writes(
        usage_client(), os.environ["GRAPH_TABLE"], TENANT, SYSTEM, OTHER_SYSTEM
    )
