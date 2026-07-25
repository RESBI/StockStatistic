"""任务历史（已在 core.py 实现）。"""
from __future__ import annotations


def get_task_history(dispatcher, limit: int = 100, state: str = None) -> dict:
    return dispatcher.task_history(limit=limit, state=state)


__all__ = ["get_task_history"]
