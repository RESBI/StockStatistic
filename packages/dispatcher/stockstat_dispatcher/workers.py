"""WorkerRegistry — Worker 注册/心跳/超时/统计。"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcfromtimestamp(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)
from typing import Optional


@dataclass
class WorkerRecord:
    worker_id: str
    alias: str = ""
    address: str = ""
    port: int = 0
    concurrency: int = 1
    hardware: dict = field(default_factory=dict)
    capabilities: list = field(default_factory=list)
    stockstat_version: str = ""
    labels: dict = field(default_factory=dict)
    preemptable: bool = False
    status: str = "online"
    last_heartbeat: float = field(default_factory=time.time)
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    avg_task_duration_s: float = 0.0
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_load: dict = field(default_factory=dict)


class WorkerRegistry:
    """Worker 注册表 — 注册/心跳/超时/统计。"""

    def __init__(self, offline_timeout: float = 30.0):
        self._workers: dict = {}
        self._offline_timeout = offline_timeout
        self._lock = threading.Lock()

    def register(self, msg: dict) -> str:
        wid = msg.get("worker_id") or str(uuid.uuid4())
        with self._lock:
            self._workers[wid] = WorkerRecord(
                worker_id=wid,
                alias=msg.get("alias", wid),
                address=msg.get("address", ""),
                port=int(msg.get("port", 0)),
                concurrency=int(msg.get("concurrency", 1)),
                hardware=msg.get("hardware", {}),
                capabilities=list(msg.get("capabilities", [])),
                stockstat_version=msg.get("stockstat_version", ""),
                labels=msg.get("labels", {}),
                preemptable=bool(msg.get("preemptable", False)),
            )
        return wid

    def update_heartbeat(self, msg: dict) -> None:
        wid = msg.get("worker_id")
        if not wid:
            return
        with self._lock:
            w = self._workers.get(wid)
            if w is None:
                return
            w.last_heartbeat = time.time()
            w.last_load = msg.get("load", {})
            w.active_tasks = int(msg.get("active_tasks", 0))
            w.completed_tasks = int(msg.get("completed_tasks", w.completed_tasks))
            w.failed_tasks = int(msg.get("failed_tasks", w.failed_tasks))
            w.avg_task_duration_s = float(msg.get("avg_task_duration_s", w.avg_task_duration_s))
            w.status = msg.get("status", "online")
            if w.active_tasks >= w.concurrency and w.status == "online":
                w.status = "busy"
            elif w.active_tasks < w.concurrency and w.status == "busy":
                w.status = "online"

    def unregister(self, worker_id: str) -> None:
        with self._lock:
            if worker_id in self._workers:
                self._workers[worker_id].status = "offline"

    def increment_active(self, worker_id: str) -> None:
        with self._lock:
            w = self._workers.get(worker_id)
            if w:
                w.active_tasks += 1
                if w.active_tasks >= w.concurrency:
                    w.status = "busy"

    def decrement_active(self, worker_id: str, completed: bool = True,
                          failed: bool = False) -> None:
        with self._lock:
            w = self._workers.get(worker_id)
            if w:
                w.active_tasks = max(0, w.active_tasks - 1)
                if completed:
                    w.completed_tasks += 1
                if failed:
                    w.failed_tasks += 1
                if w.active_tasks < w.concurrency and w.status == "busy":
                    w.status = "online"

    def check_timeouts(self) -> list:
        now = time.time()
        timed_out = []
        with self._lock:
            for w in self._workers.values():
                if w.status in ("online", "busy"):
                    if now - w.last_heartbeat > self._offline_timeout:
                        w.status = "offline"
                        timed_out.append(w.worker_id)
        return timed_out

    def list_workers(self, *, include_offline: bool = False,
                     include_hardware: bool = True,
                     filter_labels: Optional[dict] = None) -> list:
        result = []
        with self._lock:
            for w in self._workers.values():
                if w.status == "offline" and not include_offline:
                    continue
                if filter_labels:
                    if not all(w.labels.get(k) == v for k, v in filter_labels.items()):
                        continue
                d = {
                    "worker_id": w.worker_id,
                    "alias": w.alias,
                    "address": w.address,
                    "port": w.port,
                    "status": w.status,
                    "concurrency": w.concurrency,
                    "active_tasks": w.active_tasks,
                    "completed_tasks": w.completed_tasks,
                    "failed_tasks": w.failed_tasks,
                    "avg_task_duration_s": w.avg_task_duration_s,
                    "last_heartbeat": _utcfromtimestamp(w.last_heartbeat).isoformat(),
                    "capabilities": w.capabilities,
                    "stockstat_version": w.stockstat_version,
                    "labels": w.labels,
                    "load": w.last_load,
                }
                if include_hardware:
                    d["hardware"] = w.hardware
                result.append(d)
        return result

    def stats(self) -> dict:
        with self._lock:
            total = len(self._workers)
            online = sum(1 for w in self._workers.values() if w.status == "online")
            busy = sum(1 for w in self._workers.values() if w.status == "busy")
            offline = sum(1 for w in self._workers.values() if w.status == "offline")
            total_concurrency = sum(w.concurrency for w in self._workers.values())
            available = sum(
                max(0, w.concurrency - w.active_tasks) for w in self._workers.values()
                if w.status in ("online", "busy"))
            active = sum(w.active_tasks for w in self._workers.values())
            completed = sum(w.completed_tasks for w in self._workers.values())
            failed = sum(w.failed_tasks for w in self._workers.values())
        return {
            "total_workers": total,
            "online_workers": online,
            "busy_workers": busy,
            "offline_workers": offline,
            "total_concurrency": total_concurrency,
            "available_concurrency": available,
            "active_tasks": active,
            "total_completed": completed,
            "total_failed": failed,
        }

    def get(self, worker_id: str) -> Optional[WorkerRecord]:
        with self._lock:
            return self._workers.get(worker_id)


__all__ = ["WorkerRegistry", "WorkerRecord"]
