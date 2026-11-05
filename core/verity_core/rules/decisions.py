"""Which decisions still count at a point in time (ADR 0020). Pure: it takes an explicit `as_of`.

A decision replaces earlier ones by naming them in `supersedes`. That is permanent: once the
superseding decision exists, the old one is out for good, even after the new one expires, so
an expired correction never brings a mistake back.
"""

from collections.abc import Iterable
from datetime import datetime

from verity_core.model.evidence import Evidence


def superseded_decision_ids(evidence: Iterable[Evidence], as_of: datetime) -> frozenset[str]:
    """IDs of decisions named by a decision collected at or before `as_of`."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    return frozenset(
        decision_id
        for e in evidence
        if e.collected_at <= as_of
        for decision_id in (e.content or {}).get("supersedes", ())
    )
