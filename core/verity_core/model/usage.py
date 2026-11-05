"""Usage records: evidence of actual AI usage, as opposed to infrastructure merely existing
(architecture section D, stage 6). Written by the `verity_ai` adapters through a `UsageSink`.
They are append-only and live beside the graph, not in it: `load_graph` never returns them.
"""

from typing import Annotated
from uuid import UUID

from pydantic import Field, field_validator

from verity_core.model.base import UtcDatetime, VerityRecord
from verity_core.model.enums import NodeType, Source
from verity_core.model.ids import check_id


class UsageRecord(VerityRecord):
    tenant: str = Field(min_length=1)
    # Created once by the caller and reused on a retry, which makes a retried write idempotent.
    usage_id: UUID
    system_id: str
    provider_id: str
    model_id: str
    timestamp: UtcDatetime
    token_estimate: Annotated[int, Field(ge=0)]
    source: Source

    @field_validator("system_id")
    @classmethod
    def _system(cls, value: str) -> str:
        return check_id(value, NodeType.AI_SYSTEM)

    @field_validator("provider_id")
    @classmethod
    def _provider(cls, value: str) -> str:
        return check_id(value, NodeType.PROVIDER)

    @field_validator("model_id")
    @classmethod
    def _model(cls, value: str) -> str:
        return check_id(value, NodeType.MODEL)
