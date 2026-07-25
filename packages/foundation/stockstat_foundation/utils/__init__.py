"""Foundation utils — 通用辅助函数。"""
from __future__ import annotations

from .serialization import estimate_data_size, choose_data_dispatch, resolve_data_dispatch
from .timing import Timeout, now_iso, elapsed_since

__all__ = [
    "estimate_data_size", "choose_data_dispatch", "resolve_data_dispatch",
    "Timeout", "now_iso", "elapsed_since",
]
