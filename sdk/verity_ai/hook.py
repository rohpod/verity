"""The usage hook both adapters call after a successful response (ADR 0023, decision 7)."""

import logging
from collections.abc import Callable

UsageHook = Callable[[int], None]  # receives the total token count

log = logging.getLogger("verity_ai")


def notify(usage: UsageHook | None, tokens: int) -> None:
    """Telemetry never fails the call: a failed write is logged by exception type only."""
    if usage is None:
        return
    try:
        usage(tokens)
    except Exception as error:
        log.warning("usage_write_failed %s", type(error).__name__)
