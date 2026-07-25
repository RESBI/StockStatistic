"""Foundation contracts — Protocol 契约层。"""
from __future__ import annotations

from .compute import (
    ComputeBackend, TaskRef, TaskInfo, TaskState, TaskPriority,
)
from .transport import Transport
from .storage import StorageBackend
from .cache import Cache
from .codec import Codec
from .plugin import Plugin
from .renderer import Renderer
from .events import EventSubscriber, Event

__all__ = [
    "ComputeBackend", "TaskRef", "TaskInfo", "TaskState", "TaskPriority",
    "Transport", "StorageBackend", "Cache", "Codec", "Plugin", "Renderer",
    "EventSubscriber", "Event",
]
