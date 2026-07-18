"""Worker registry — tracks registered workers, heartbeats, and state.

V2 §12.13: Workers register on startup with hardware info and alias,
send periodic heartbeats with load info, and are marked offline if
heartbeat times out (default 30s).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class WorkerEntry:
    """A registered worker's current state."""
    worker_id: str
    alias: str
    address: str = ""
    port: int = 0
    concurrency: int = 1
    capabilities: list = field(default_factory=list)
    stockstat_version: str = ""
    hardware: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)
    status: str = "online"  # online / busy / draining / offline
    last_heartbeat: float = 0.0  # unix timestamp
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    avg_task_duration_s: float = 0.0
    load: dict = field(default_factory=dict)
    preemptable: bool = False
    registered_at: float = 0.0


class WorkerRegistry:
    """Thread-safe registry of all workers.

    The Dispatcher uses this to:
    - Route tasks to workers with matching capabilities
    - Track worker health via heartbeat timeouts
    - Provide cluster_info() data
    - Mark workers offline when they stop heartbeating
    """

    def __init__(self, offline_timeout: float = 30.0):
        self._workers: dict[str, WorkerEntry] = {}
        self._lock = threading.Lock()
        self._offline_timeout = offline_timeout

    def register(self, msg: dict) -> str:
        """Register a new worker. Returns worker_id."""
        wid = msg.get("worker_id") or msg.get("id", "")
        if not wid:
            import uuid
            wid = str(uuid.uuid4())
        entry = WorkerEntry(
            worker_id=wid,
            alias=msg.get("alias", wid),
            address=msg.get("address", ""),
            port=msg.get("port", 0),
            concurrency=msg.get("concurrency", 1),
            capabilities=msg.get("capabilities", []),
            stockstat_version=msg.get("stockstat_version", ""),
            hardware=msg.get("hardware", {}),
            labels=msg.get("labels", {}),
            status="online",
            last_heartbeat=time.time(),
            registered_at=time.time(),
            preemptable=msg.get("preemptable", False),
        )
        with self._lock:
            self._workers[wid] = entry
        return wid

    def heartbeat(self, msg: dict) -> None:
        """Update worker heartbeat and load info."""
        wid = msg.get("worker_id", "")
        with self._lock:
            w = self._workers.get(wid)
            if w is None:
                return
            w.last_heartbeat = time.time()
            w.load = msg.get("load", {})
            w.active_tasks = msg.get("active_tasks", 0)
            w.completed_tasks = msg.get("completed_tasks", 0)
            w.failed_tasks = msg.get("failed_tasks", 0)
            w.avg_task_duration_s = msg.get("avg_task_duration_s", 0.0)
            # Update status based on load
            if w.active_tasks >= w.concurrency:
                w.status = "busy"
            else:
                w.status = "online"

    def unregister(self, worker_id: str) -> None:
        """Mark a worker as offline (graceful shutdown)."""
        with self._lock:
            w = self._workers.get(worker_id)
            if w:
                w.status = "offline"

    def get(self, worker_id: str) -> Optional[WorkerEntry]:
        with self._lock:
            return self._workers.get(worker_id)

    def list_online(self, capability: str = None) -> list[WorkerEntry]:
        """List online workers, optionally filtered by capability."""
        now = time.time()
        with self._lock:
            result = []
            for w in self._workers.values():
                # Check heartbeat timeout
                if w.status in ("online", "busy"):
                    if now - w.last_heartbeat > self._offline_timeout:
                        w.status = "offline"
                if w.status in ("online", "busy"):
                    if capability is None or capability in w.capabilities:
                        result.append(w)
            return result

    def list_all(self) -> list[WorkerEntry]:
        with self._lock:
            return list(self._workers.values())

    def check_timeouts(self) -> list[str]:
        """Mark workers with stale heartbeats as offline. Returns affected IDs."""
        now = time.time()
        timed_out = []
        with self._lock:
            for w in self._workers.values():
                if w.status in ("online", "busy"):
                    if now - w.last_heartbeat > self._offline_timeout:
                        w.status = "offline"
                        timed_out.append(w.worker_id)
        return timed_out

    def increment_active(self, worker_id: str) -> None:
        with self._lock:
            w = self._workers.get(worker_id)
            if w:
                w.active_tasks += 1
                if w.active_tasks >= w.concurrency:
                    w.status = "busy"

    def decrement_active(self, worker_id: str, *, completed: bool = True,
                         failed: bool = False) -> None:
        with self._lock:
            w = self._workers.get(worker_id)
            if w:
                w.active_tasks = max(0, w.active_tasks - 1)
                if completed:
                    w.completed_tasks += 1
                if failed:
                    w.failed_tasks += 1
                if w.status == "busy" and w.active_tasks < w.concurrency:
                    w.status = "online"

    def stats(self) -> dict:
        """Aggregate statistics for cluster_info()."""
        with self._lock:
            workers = list(self._workers.values())
        total = len(workers)
        online = sum(1 for w in workers if w.status in ("online", "busy"))
        offline = total - online
        total_conc = sum(w.concurrency for w in workers)
        active = sum(w.active_tasks for w in workers)
        completed = sum(w.completed_tasks for w in workers)
        failed = sum(w.failed_tasks for w in workers)
        return {
            "total_workers": total,
            "online_workers": online,
            "offline_workers": offline,
            "total_concurrency": total_conc,
            "available_concurrency": max(0, total_conc - active),
            "active_tasks": active,
            "total_completed": completed,
            "total_failed": failed,
        }
