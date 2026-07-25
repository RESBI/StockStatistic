"""统一日志（trace_id 透传）。"""
from __future__ import annotations

import contextvars
import logging
import sys
from typing import Optional

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default=""
)


def set_trace_id(trace_id: str) -> contextvars.Token:
    return _trace_id_var.set(trace_id or "")


def get_trace_id() -> str:
    return _trace_id_var.get()


def reset_trace_id(token: contextvars.Token) -> None:
    _trace_id_var.reset(token)


class TraceIdFilter(logging.Filter):
    """日志过滤器 — 注入 trace_id 字段。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get() or "-"
        return True


def get_logger(name: str = "stockstat", level: Optional[int] = None) -> logging.Logger:
    """获取配置好的 logger。"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        fmt = "%(asctime)s [%(levelname)s] [%(trace_id)s] %(name)s: %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        handler.addFilter(TraceIdFilter())
        logger.addHandler(handler)
        logger.setLevel(level or logging.INFO)
        logger.propagate = False
    elif level is not None:
        logger.setLevel(level)
    return logger


__all__ = ["get_logger", "set_trace_id", "get_trace_id", "reset_trace_id", "TraceIdFilter"]
