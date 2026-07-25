"""Worker 进程 — 注册/心跳/拉取/执行/回传。"""
from __future__ import annotations

import base64
import os
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional

from stockstat_foundation import TaskSpec, CloudpickleCodec
from stockstat_foundation.errors import TaskError

from .executor import TaskExecutor
from .register import detect_hardware, get_current_load
from .handlers import ALL_TASK_TYPES

__version__ = "3.1.0"


class Worker:
    """Compute Worker — 独立运行的计算节点。

    生命周期：
        启动 → detect_hardware() → POST /dispatch/register
                            ↓
            心跳线程（10s）→ POST /dispatch/heartbeat
                            ↓
            主循环 → POST /dispatch/assign → 执行 → POST /dispatch/complete
                            ↓
            SIGTERM → stop() → 等待活跃任务 → POST /dispatch/unregister → 退出
    """

    def __init__(self, dispatcher_url: str, *,
                 concurrency: Optional[int] = None,
                 alias: Optional[str] = None,
                 labels: Optional[dict] = None,
                 capabilities: Optional[list] = None,
                 preemptable: bool = False,
                 poll_interval: float = 1.0,
                 heartbeat_interval: float = 10.0,
                 http_client=None):
        self._url = dispatcher_url.rstrip("/")
        self._concurrency = concurrency or os.cpu_count() or 1
        self._alias = alias or f"{socket.gethostname()}-{os.getpid()}"
        self._labels = labels or {}
        self._capabilities = capabilities or list(ALL_TASK_TYPES)
        self._preemptable = preemptable
        self._poll_interval = poll_interval
        self._heartbeat_interval = heartbeat_interval
        self._executor_pool = ThreadPoolExecutor(max_workers=self._concurrency)
        self._active_futures: dict = {}
        self._stopping = threading.Event()
        self._draining = False
        self._preempted: set = set()
        self._worker_id: Optional[str] = None
        self._completed = 0
        self._failed = 0
        if http_client is not None:
            self._http = http_client
        else:
            import httpx
            self._http = httpx.Client(timeout=30)
        self._executor = TaskExecutor(worker=self)
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._registered = threading.Event()

    @property
    def worker_id(self) -> Optional[str]:
        return self._worker_id

    @property
    def alias(self) -> str:
        return self._alias

    def start(self) -> None:
        """阻塞入口（CLI 主循环）。"""
        self._register()
        self._start_heartbeat()
        try:
            while not self._stopping.is_set():
                if self._draining and not self._active_futures:
                    break
                self._poll_and_execute()
                self._stopping.wait(self._poll_interval)
        finally:
            self._unregister()
            self._http.close()

    def start_background(self) -> None:
        """后台线程（测试/嵌入）。"""
        t = threading.Thread(target=self.start, daemon=True)
        t.start()

    def stop(self) -> None:
        self._stopping.set()

    def drain(self) -> None:
        self._draining = True

    def preempt(self, slice_id: str) -> bool:
        self._preempted.add(slice_id)
        return True

    def resume(self, slice_id: str) -> bool:
        self._preempted.discard(slice_id)
        return True

    def join(self, timeout: float = 10.0) -> None:
        self._stopping.set()
        for future in list(self._active_futures.values()):
            try:
                future.result(timeout=timeout)
            except Exception:
                pass

    def wait_registered(self, timeout: float = 10.0) -> bool:
        return self._registered.wait(timeout=timeout)

    # ── 内部方法 ──

    def _register(self):
        hardware = detect_hardware()
        try:
            resp = self._http.post(f"{self._url}/dispatch/register", json={
                "worker_id": str(uuid.uuid4()),
                "alias": self._alias,
                "address": socket.gethostname(),
                "port": 0,
                "concurrency": self._concurrency,
                "hardware": hardware,
                "capabilities": self._capabilities,
                "stockstat_version": __version__,
                "labels": self._labels,
                "preemptable": self._preemptable,
            })
            self._worker_id = resp.json().get("worker_id")
            self._registered.set()
        except Exception:
            pass

    def _start_heartbeat(self):
        def loop():
            while not self._stopping.is_set():
                try:
                    self._send_heartbeat()
                except Exception:
                    pass
                self._stopping.wait(self._heartbeat_interval)
        self._heartbeat_thread = threading.Thread(target=loop, daemon=True)
        self._heartbeat_thread.start()

    def _send_heartbeat(self):
        if not self._worker_id:
            return
        load = get_current_load()
        self._http.post(f"{self._url}/dispatch/heartbeat", json={
            "worker_id": self._worker_id,
            "alias": self._alias,
            "timestamp": time.time(),
            "load": load,
            "active_tasks": len(self._active_futures),
            "completed_tasks": self._completed,
            "failed_tasks": self._failed,
            "status": "draining" if self._draining else "online",
        })

    def _poll_and_execute(self):
        if len(self._active_futures) >= self._concurrency:
            return
        if not self._worker_id:
            return
        try:
            resp = self._http.post(f"{self._url}/dispatch/assign", json={
                "worker_id": self._worker_id,
                "capabilities": self._capabilities,
            })
            assignment = resp.json()
        except Exception:
            return
        if assignment.get("task_spec") is None:
            return
        future = self._executor_pool.submit(self._execute, assignment)
        slice_id = assignment["task_spec"]["task_id"]
        self._active_futures[slice_id] = future

    def _execute(self, assignment: dict):
        slice_id = assignment["task_spec"]["task_id"]
        try:
            result = self._executor.run(assignment)
            self._send_complete(slice_id, result)
            self._completed += 1
        except Exception as e:
            self._send_fail(slice_id, e)
            self._failed += 1
        finally:
            self._active_futures.pop(slice_id, None)

    def _send_complete(self, slice_id: str, result: dict):
        result_bytes = CloudpickleCodec().encode(result["result"])
        self._http.post(f"{self._url}/dispatch/complete", json={
            "worker_id": self._worker_id,
            "slice_id": slice_id,
            "result": base64.b64encode(result_bytes).decode("ascii"),
        })

    def _send_fail(self, slice_id: str, error: Exception):
        import traceback
        self._http.post(f"{self._url}/dispatch/fail", json={
            "worker_id": self._worker_id,
            "slice_id": slice_id,
            "error": {
                "error_code": "COMPUTE_FAILED",
                "error_message": str(error),
                "traceback": traceback.format_exc(),
                "retryable": False,
            },
        })

    def _send_partial(self, task_id: str, partial: dict):
        if not self._worker_id:
            return
        try:
            self._http.post(f"{self._url}/dispatch/partial", json={
                "slice_id": task_id,
                "partial": partial,
            })
        except Exception:
            pass

    def _unregister(self):
        if not self._worker_id:
            return
        try:
            self._http.post(f"{self._url}/dispatch/unregister/{self._worker_id}")
        except Exception:
            pass


__all__ = ["Worker"]
