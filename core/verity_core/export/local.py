"""The fixture source (ADR 0029, decision 1): crawl the recorded estate into memory and assess it.

Nothing is read from AWS. The clock is fixed at `as_of`, so the same inputs give the same graph
and so the same bytes.
"""

from datetime import datetime
from pathlib import Path

import networkx as nx

from verity_core.assess.apply import apply_assessment
from verity_core.content.loader import Content
from verity_core.content.seed import seed
from verity_core.discovery.collectors import FixtureCollector
from verity_core.discovery.pipeline import crawl
from verity_core.graph.memory import InMemoryRepository


def local_graph(content: Content, fixture: Path, as_of: datetime) -> nx.MultiDiGraph:
    if content.rules is None or content.signals is None:
        raise ValueError("applicability.yaml and ai_signals.yaml are needed")

    def clock() -> datetime:
        return as_of

    repo = InMemoryRepository(content.tenant, clock)
    seed(repo, content, clock)
    crawl(repo, content, FixtureCollector(fixture), clock)
    apply_assessment(repo, content.rules, content.dates, as_of, clock)
    return repo.load_graph()
