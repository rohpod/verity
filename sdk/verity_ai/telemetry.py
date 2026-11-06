"""`UsageRecorder`: a usage hook that writes one `UsageRecord` per model call (D8).

The only `verity_ai` module that imports `verity_core`. Records are labelled simulated, because
the providers are mocks. It is for third-party model calls only: an in-house model has no
provider, so Talent Screening writes none (ADR 0023, decision 6).
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import uuid4

from verity_core.model.enums import Source
from verity_core.model.usage import UsageRecord


class UsageRecorder:
    def __init__(
        self,
        sink: Any,
        *,
        tenant: str,
        system_id: str,
        provider_id: str,
        model_id: str,
        clock: Callable[[], datetime],
    ):
        self._sink = sink
        self._tenant = tenant
        self._system_id = system_id
        self._provider_id = provider_id
        self._model_id = model_id
        self._clock = clock

    def __call__(self, tokens: int) -> None:
        self._sink.append_usage(
            UsageRecord(
                tenant=self._tenant,
                usage_id=uuid4(),
                system_id=self._system_id,
                provider_id=self._provider_id,
                model_id=self._model_id,
                timestamp=self._clock(),
                token_estimate=tokens,
                source=Source.SIMULATED,
            )
        )
