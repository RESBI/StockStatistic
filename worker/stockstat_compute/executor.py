"""TaskExecutor — routes TaskSpec to the appropriate handler.

Wraps the shared handlers from stockstat._core.compute.handlers
and handles data deserialization + result serialization.
"""
from __future__ import annotations

import base64
from typing import Any, Optional


class TaskExecutor:
    """Execute a single TaskSpec slice.

    Uses the shared dispatch() function from stockstat._core.compute.handlers
    so that Local and Worker execution paths are identical.
    """

    def __init__(self, worker=None):
        self._worker = worker
        self._completed = 0
        self._failed = 0
        self._total_duration = 0.0

    def run(self, spec, data: dict = None, data_ref: str = None,
            data_bytes: bytes = None) -> dict:
        """Execute a task slice and return a result dict.

        Returns:
            {"slice_id": str, "result": Any, "result_codec": str}
        Raises:
            Exception on execution failure
        """
        import time as _time
        from stockstat._core.compute.handlers import dispatch, deserialize_result
        from stockstat._core.codec import CloudpickleCodec

        # Resolve data
        if data is None and data_bytes is not None:
            data = CloudpickleCodec().decode(data_bytes)
        elif data is None and data_ref is not None:
            # Worker should have fetched data from Dispatcher already
            raise ValueError("No data provided (neither inline nor fetched)")

        # Progress callback
        def on_progress(completed, total):
            if self._worker:
                self._worker._send_partial(spec.task_id, {
                    "completed": completed, "total": total,
                    "progress": completed / total if total > 0 else 0,
                })

        # Execute
        t0 = _time.time()
        result = dispatch(spec, data, on_progress=on_progress)
        duration = _time.time() - t0

        self._completed += 1
        self._total_duration += duration

        return {
            "slice_id": spec.task_id,
            "result": result,
            "result_codec": "cloudpickle",
            "duration_s": duration,
        }

    @property
    def avg_duration_s(self) -> float:
        return self._total_duration / self._completed if self._completed > 0 else 0
