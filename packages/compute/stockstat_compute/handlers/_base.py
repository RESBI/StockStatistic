"""Handler 基类与辅助 — Stream / is_stream_aware / register / HANDLERS。

所有 handler 用 `from .._base import register` 注册。
"""
from __future__ import annotations

from typing import Any, Callable, Optional
import inspect

from stockstat_foundation.errors import WorkerCapabilityError


class Stream:
    """数据流 — 同时支持迭代模式与 collect 模式。"""

    def __init__(self, chunks=None, data=None):
        self._chunks = chunks
        self._collected = data

    def __iter__(self):
        if self._chunks:
            for chunk in self._chunks:
                yield chunk
        elif self._collected is not None:
            yield self._collected

    def collect(self) -> Any:
        if self._collected is None and self._chunks:
            import pandas as pd
            self._collected = pd.concat(list(self._chunks))
        return self._collected

    @classmethod
    def from_data(cls, data) -> "Stream":
        return cls(data=data)


def is_stream_aware(handler: Callable) -> bool:
    """检查 handler 签名是否声明 Stream 参数。"""
    try:
        sig = inspect.signature(handler)
    except (ValueError, TypeError):
        return False
    for param in sig.parameters.values():
        if param.annotation is Stream:
            return True
        ann = str(param.annotation)
        if "Stream" in ann:
            return True
    return getattr(handler, "__stream_aware__", False)


# ── Handler 注册表 ──

HANDLERS: dict = {}


def register(task_type: str):
    """handler 注册装饰器。"""
    def decorator(func):
        HANDLERS[task_type] = func
        return func
    return decorator


def dispatch(spec, data: Any = None, *,
             worker: Optional[Any] = None,
             on_progress: Optional[Callable] = None) -> Any:
    """路由 TaskSpec 到对应 handler。"""
    # 如果 data 为 None，尝试从 params._inline_data 提取
    if data is None and spec.compute_spec.params.get("_inline_data") is not None:
        data = spec.compute_spec.params.pop("_inline_data")
    task_type = spec.compute_spec.task_type
    handler = HANDLERS.get(task_type)
    if handler is None:
        raise WorkerCapabilityError(
            f"No handler for task_type: {task_type}",
            code="WORKER_CAPABILITY_INSUFFICIENT",
            context={"task_type": task_type,
                     "available": sorted(HANDLERS.keys())},
        )
    progress_cb = on_progress
    if progress_cb is None and worker is not None:
        progress_cb = _make_progress(worker, spec)

    if is_stream_aware(handler):
        stream = Stream.from_data(data)
        return handler(spec, stream, on_progress=progress_cb)
    return handler(spec, data, on_progress=progress_cb)


def _make_progress(worker, spec):
    def on_progress(completed, total):
        if worker is not None and hasattr(worker, "_send_partial"):
            worker._send_partial(spec.task_id, {
                "completed": completed, "total": total,
                "progress": completed / total if total > 0 else 0,
            })
    return on_progress


def list_task_types() -> list:
    return sorted(HANDLERS.keys())


__all__ = [
    "Stream", "is_stream_aware",
    "HANDLERS", "register", "dispatch", "list_task_types",
]
