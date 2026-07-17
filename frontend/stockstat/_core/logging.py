"""Structured logging for v2.0."""
from __future__ import annotations

import logging
from typing import Any, Optional


class StructuredLogger:
    """Logger that emits structured context with each message.

    Wraps Python's stdlib :mod:`logging` with context fields
    (e.g. ``request_id``, ``symbol``, ``source``).
    """

    def __init__(self, name: str = "stockstat") -> None:
        self._logger = logging.getLogger(name)
        self._context: dict[str, Any] = {}

    def bind(self, **fields: Any) -> "StructuredLogger":
        """Return a new logger with additional context fields."""
        new = StructuredLogger(self._logger.name)
        new._context = {**self._context, **fields}
        return new

    def _emit(self, level: str, msg: str, **extra: Any) -> None:
        ctx = {**self._context, **extra}
        if ctx:
            prefix = " ".join(f"{k}={v}" for k, v in ctx.items())
            msg = f"[{prefix}] {msg}"
        getattr(self._logger, level)(msg)

    def debug(self, msg: str, **extra: Any) -> None:
        self._emit("debug", msg, **extra)

    def info(self, msg: str, **extra: Any) -> None:
        self._emit("info", msg, **extra)

    def warning(self, msg: str, **extra: Any) -> None:
        self._emit("warning", msg, **extra)

    def error(self, msg: str, **extra: Any) -> None:
        self._emit("error", msg, **extra)

    def exception(self, msg: str, **extra: Any) -> None:
        self._emit("exception", msg, **extra)


# Module-level singleton
_logger: Optional[StructuredLogger] = None


def get_logger() -> StructuredLogger:
    global _logger
    if _logger is None:
        _logger = StructuredLogger()
    return _logger
