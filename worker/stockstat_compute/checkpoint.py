"""Checkpoint — V3 P6 §13.3 task state serialization for preemption.

When a high-priority task preempts a low-priority one, the Worker
serializes the current task state to a checkpoint, then resumes it
later when resources become available.

Currently supports:
- grid_search: serializes the param_slice index + completed results
- custom: trivial (no state)
- Future: backtest state, batch_backtest progress
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Checkpoint:
    """Serialized task state for preemption resume.

    Fields:
        task_id: the slice ID being checkpointed
        task_type: handler type (grid_search / batch_backtest / ...)
        progress: 0.0 ~ 1.0
        completed_items: list of completed sub-results (e.g. grid points)
        remaining_items: list of items still to process
        params: handler-specific state
    """
    task_id: str
    task_type: str
    progress: float = 0.0
    completed_items: list = field(default_factory=list)
    remaining_items: list = field(default_factory=list)
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "progress": self.progress,
            "completed_items": self.completed_items,
            "remaining_items": self.remaining_items,
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Checkpoint":
        return cls(
            task_id=d["task_id"],
            task_type=d.get("task_type", ""),
            progress=float(d.get("progress", 0.0)),
            completed_items=list(d.get("completed_items", [])),
            remaining_items=list(d.get("remaining_items", [])),
            params=dict(d.get("params", {})),
        )


class CheckpointStore:
    """In-memory checkpoint store (P6).

    Future: persist to Redis / disk for cross-process resume.
    """

    def __init__(self):
        self._checkpoints: dict[str, Checkpoint] = {}

    def save(self, ckpt: Checkpoint) -> None:
        self._checkpoints[ckpt.task_id] = ckpt

    def load(self, task_id: str) -> Optional[Checkpoint]:
        return self._checkpoints.get(task_id)

    def delete(self, task_id: str) -> None:
        self._checkpoints.pop(task_id, None)

    def list(self) -> list[str]:
        return list(self._checkpoints.keys())


# Global singleton (per-process; Worker uses this for preempt/resume)
_global_store = CheckpointStore()


def get_checkpoint_store() -> CheckpointStore:
    """Get the global checkpoint store."""
    return _global_store
