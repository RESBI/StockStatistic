from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from .base import ContractModel
from .ids import new_id
from .time import normalize_utc, utc_now
from .version import PROTOCOL_VERSION

CONTROL_MEDIA_TYPE = "application/vnd.stockstat.control+json; version=3.1"


class TraceContext(ContractModel):
    traceparent: str
    tracestate: str | None = None


class ControlMessage(ContractModel):
    protocol: str = "stockstat-control"
    protocol_version: str = PROTOCOL_VERSION
    message_type: str
    message_id: str = Field(default_factory=new_id)
    correlation_id: str | None = None
    causation_id: str | None = None
    sent_at: datetime = Field(default_factory=utc_now)
    deadline_at: datetime | None = None
    trace: TraceContext | None = None
    content_schema: str
    content: dict[str, Any]

    @field_validator("protocol_version")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        if value.split(".", 1)[0] != PROTOCOL_VERSION.split(".", 1)[0]:
            raise ValueError("unsupported protocol major version")
        return value

    @field_validator("sent_at", "deadline_at")
    @classmethod
    def validate_time(cls, value: datetime | None) -> datetime | None:
        return normalize_utc(value) if value is not None else None
