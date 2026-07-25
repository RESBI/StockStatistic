"""Handlers — 47 个 task_type handler 注册表 + dispatch。"""
from __future__ import annotations

# 从 _base 重新导出，方便外部使用
from ._base import (
    Stream, is_stream_aware,
    HANDLERS, register, dispatch, list_task_types,
)

# 导入所有 handler 模块以触发注册（顺序：基础 → 高级）
from . import backtest as _backtest  # noqa: E402,F401
from . import stats as _stats  # noqa: E402,F401
from . import signal as _signal  # noqa: E402,F401
from . import nonlinear as _nonlinear  # noqa: E402,F401
from . import grey as _grey  # noqa: E402,F401
from . import ml as _ml  # noqa: E402,F401
from . import portfolio as _portfolio  # noqa: E402,F401


ALL_TASK_TYPES = list(HANDLERS.keys())


__all__ = [
    "Stream", "is_stream_aware",
    "HANDLERS", "register", "dispatch", "list_task_types",
    "ALL_TASK_TYPES",
]
