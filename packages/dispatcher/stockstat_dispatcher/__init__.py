"""stockstat-dispatcher — StockStat V3.1 分发端。"""
from __future__ import annotations

__version__ = "3.1.0"

from .core import Dispatcher
from .queue import MemoryTaskQueue, RedisTaskQueue, build_queue
from .workers import WorkerRegistry, WorkerRecord
from .prefetch import DataCache
from .shard import shard_task
from .merge import merge_results
from .routes import create_dispatcher_router
from .plugin import DispatcherPlugin
from .app import DispatcherApp
from .cluster import ClusterManager

__all__ = [
    "__version__",
    "Dispatcher",
    "MemoryTaskQueue", "RedisTaskQueue", "build_queue",
    "WorkerRegistry", "WorkerRecord",
    "DataCache",
    "shard_task", "merge_results",
    "create_dispatcher_router",
    "DispatcherPlugin", "DispatcherApp",
    "ClusterManager",
]
