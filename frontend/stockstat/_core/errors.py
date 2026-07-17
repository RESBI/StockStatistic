"""Error classification for v2.0."""
from __future__ import annotations

from typing import Any, Optional


class AppError(Exception):
    """Base application error with error code and context.

    Attributes:
        code: Machine-readable error code (e.g. ``"DATA_NOT_FOUND"``).
        message: Human-readable message.
        context: Additional structured context.
        recoverable: Whether the caller may retry.
    """
    code: str = "INTERNAL_ERROR"
    recoverable: bool = False

    def __init__(
        self,
        message: str = "",
        code: Optional[str] = None,
        context: Optional[dict] = None,
        recoverable: Optional[bool] = None,
    ) -> None:
        self.message = message or self.code
        if code is not None:
            self.code = code
        self.context = context or {}
        if recoverable is not None:
            self.recoverable = recoverable
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "context": self.context,
            "recoverable": self.recoverable,
        }


class DataNotFoundError(AppError):
    code = "DATA_NOT_FOUND"


class SymbolNotFoundError(AppError):
    code = "SYMBOL_NOT_FOUND"


class AdapterError(AppError):
    code = "ADAPTER_FAILED"
    recoverable = True


class InvalidParamsError(AppError):
    code = "INVALID_PARAMS"


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    recoverable = True


class LookaheadError(AppError):
    code = "LOOKAHEAD_VIOLATION"


class PluginNotFoundError(AppError):
    code = "PLUGIN_NOT_FOUND"
