"""TaskExecutor — 路由 TaskSpec 到对应 handler（Worker 侧使用）。"""
from __future__ import annotations

import base64
import time
from typing import Any, Optional

from stockstat_foundation import TaskSpec, CloudpickleCodec

from .handlers import dispatch


class TaskExecutor:
    """任务执行器 — 路由 TaskSpec 到对应 handler。"""

    def __init__(self, worker: Optional[Any] = None):
        self._worker = worker

    def run(self, assignment: dict) -> dict:
        """执行任务分派。

        assignment = {
            "task_spec": {...},
            "data_ref": "cache://...",
            "data": "base64...",
            "data_codec": "cloudpickle",
        }
        """
        spec = TaskSpec.from_dict(assignment["task_spec"])
        # 解码数据
        data = None
        if assignment.get("data"):
            data_bytes = base64.b64decode(assignment["data"])
            data = CloudpickleCodec().decode(data_bytes)

        start = time.time()
        result = dispatch(spec, data, worker=self._worker)
        duration = time.time() - start

        return {
            "slice_id": spec.task_id,
            "result": result,
            "result_codec": "cloudpickle",
            "duration_s": duration,
        }


__all__ = ["TaskExecutor"]
