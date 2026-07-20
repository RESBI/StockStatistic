from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from .base import ContractModel


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    DATA = "data"
    COMPUTE = "compute"
    INFRASTRUCTURE = "infrastructure"
    CANCELLED = "cancelled"
    SECURITY = "security"


class ErrorInfo(ContractModel):
    code: str
    category: ErrorCategory
    message: str
    retryable: bool = False
    error_id: str | None = None
    trace_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    causes: tuple[ErrorInfo, ...] = ()


class StockStatProtocolError(RuntimeError):
    def __init__(self, info: ErrorInfo):
        super().__init__(info.message)
        self.info = info
