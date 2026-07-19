"""Worker process — connects to Dispatcher, polls for tasks, executes, reports.

Lifecycle:
1. start() → detect hardware → register → start heartbeat thread
2. Main loop: poll /dispatch/assign → execute → post /dispatch/complete
3. On drain signal: stop polling, wait for active tasks, unregister, exit
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional


class Worker:
    """Compute Worker — V2 §2.3 role.

    Connects to a Dispatcher via HTTP, polls for task assignments,
    executes them using stockstat's compute core, and posts results.
    """

    def __init__(self, dispatcher_url: str, *,
                 concurrency: int = None,
                 alias: str = None,
                 labels: dict = None,
                 capabilities: list = None,
                 preemptable: bool = False,
                 poll_interval: float = 1.0,
                 heartbeat_interval: float = 10.0):
        self._url = dispatcher_url.rstrip("/")
        self._concurrency = concurrency or os.cpu_count() or 1
        self._alias = alias or f"{socket.gethostname()}-{os.getpid()}"
        self._labels = labels or {}
        self._capabilities = capabilities or [
            "indicator", "backtest", "grid_search",
            "batch_backtest", "monte_carlo", "custom",
        ]
        self._preemptable = preemptable
        self._poll_interval = poll_interval
        self._heartbeat_interval = heartbeat_interval
        self._worker_id = str(uuid.uuid4())
        self._executor_pool = ThreadPoolExecutor(max_workers=self._concurrency)
        self._active_futures = {}
        self._stopping = threading.Event()
        self._completed = 0
        self._failed = 0
        self._total_duration = 0.0
        # P6: preemption + drain state
        self._draining = False
        self._preempted: set[str] = set()
        self._registered = False
        self._bg_thread = None

    def start(self) -> None:
        """Start the Worker: register, heartbeat, poll loop (blocking)."""
        self._start_background()
        try:
            # Wait until stop() is called (or KeyboardInterrupt)
            while not self._stopping.is_set():
                time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit):
            self._stopping.set()
        finally:
            self._unregister()
            self._executor_pool.shutdown(wait=True)
            print(f"[Worker] Stopped: completed={self._completed}, failed={self._failed}")

    def start_background(self) -> None:
        """Start the Worker in a background thread (non-blocking).

        For tests and embedding in a larger process. Caller is
        responsible for calling ``stop()`` for graceful shutdown.
        """
        self._bg_thread = threading.Thread(
            target=self._start_background, daemon=True,
            name=f"worker-{self._alias}",
        )
        self._bg_thread.start()

    def _start_background(self) -> None:
        """Internal: register, start heartbeat, run poll loop."""
        from .register import detect_hardware
        print(f"[Worker] Starting: alias={self._alias}, concurrency={self._concurrency}")
        print(f"[Worker] Dispatcher: {self._url}")
        print(f"[Worker] Capabilities: {self._capabilities}")

        # Register
        hw = detect_hardware()
        import httpx
        try:
            resp = httpx.post(f"{self._url}/dispatch/register", json={
                "worker_id": self._worker_id,
                "alias": self._alias,
                "address": socket.gethostname(),
                "port": 0,
                "concurrency": self._concurrency,
                "hardware": hw,
                "capabilities": self._capabilities,
                "stockstat_version": _get_version(),
                "labels": self._labels,
                "preemptable": self._preemptable,
            }, timeout=10)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Registration failed: {resp.status_code} {resp.text}"
                )
        except Exception as e:
            print(f"[Worker] Registration error: {e}")
            raise
        print(f"[Worker] Registered: worker_id={self._worker_id}")
        self._registered = True

        # Start heartbeat thread
        hb = threading.Thread(target=self._heartbeat_loop, daemon=True)
        hb.start()

        # Main poll loop
        try:
            self._poll_loop()
        finally:
            self._unregister()
            self._executor_pool.shutdown(wait=True)
            print(f"[Worker] Stopped: completed={self._completed}, failed={self._failed}")

    def wait_registered(self, timeout: float = 10.0) -> bool:
        """Wait until the worker has registered with the Dispatcher."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if getattr(self, "_registered", False):
                return True
            time.sleep(0.05)
        return getattr(self, "_registered", False)

    def stop(self) -> None:
        """Signal the Worker to stop (graceful drain).

        P6: marks the worker as ``draining`` — stops accepting new tasks,
        waits for active tasks to complete, then exits.
        """
        self._stopping.set()
        self._draining = True

    def drain(self) -> None:
        """V2 §13.4: graceful drain — same as stop().

        Distinct method name for the ``dispatch.drain`` message handler.
        """
        self.stop()

    def preempt(self, slice_id: str) -> bool:
        """V2 §13.3: preempt a running task.

        Saves a checkpoint (if the handler supports it) and stops the task.
        Returns True if preemption was accepted, False if not supported.

        P6 implementation: marks the task's future for cancellation;
        the handler must cooperatively check ``cancel_requested`` and
        save a checkpoint before exiting.
        """
        future = self._active_futures.get(slice_id)
        if future is None:
            return False
        # Mark for cooperative cancellation
        self._preempted.add(slice_id)
        # Cannot forcibly cancel a running thread; the handler must
        # check self._preempted and exit gracefully
        return True

    def resume(self, slice_id: str) -> bool:
        """V2 §13.3: resume a preempted task from checkpoint.

        Currently a placeholder — full resume requires the Worker to
        re-fetch the checkpoint and restart the handler from where it
        left off. P6 implementation: just acknowledge.
        """
        return slice_id in self._preempted

    def join(self, timeout: float = 10.0) -> None:
        """Wait for the background thread to finish (after stop())."""
        t = getattr(self, "_bg_thread", None)
        if t is not None:
            t.join(timeout=timeout)

    def _heartbeat_loop(self) -> None:
        from .register import get_current_load
        import httpx
        while not self._stopping.is_set():
            try:
                load = get_current_load()
                httpx.post(f"{self._url}/dispatch/heartbeat", json={
                    "worker_id": self._worker_id,
                    "alias": self._alias,
                    "load": load,
                    "active_tasks": len(self._active_futures),
                    "completed_tasks": self._completed,
                    "failed_tasks": self._failed,
                    "avg_task_duration_s": self._avg_duration(),
                    "status": "online" if not self._stopping.is_set() else "draining",
                }, timeout=5)
            except Exception:
                pass  # heartbeat failures are non-fatal
            time.sleep(self._heartbeat_interval)

    def _poll_loop(self) -> None:
        import httpx
        while not self._stopping.is_set():
            try:
                resp = httpx.post(f"{self._url}/dispatch/assign", json={
                    "worker_id": self._worker_id,
                    "capabilities": self._capabilities,
                }, timeout=self._poll_interval + 5)

                if resp.status_code == 204:
                    time.sleep(self._poll_interval)
                    continue
                if resp.status_code != 200:
                    time.sleep(self._poll_interval)
                    continue

                assignment = resp.json()
                self._execute_assignment(assignment)

            except httpx.TimeoutException:
                continue
            except Exception as e:
                print(f"[Worker] Poll error: {e}")
                time.sleep(self._poll_interval)

    def _execute_assignment(self, assignment: dict) -> None:
        """Execute a task assignment in the thread pool."""
        from stockstat._core.contracts.task import TaskSpec
        from .executor import TaskExecutor

        spec = TaskSpec.from_dict(assignment["task_spec"])
        data_ref = assignment.get("data_ref", "")
        data_bytes = assignment.get("data")  # inline data (if any)

        # Deserialize data if provided inline
        data = None
        if data_bytes:
            from stockstat._core.codec import CloudpickleCodec
            if isinstance(data_bytes, str):
                data_bytes = base64.b64decode(data_bytes)
            data = CloudpickleCodec().decode(data_bytes)

        # Submit to thread pool
        future = self._executor_pool.submit(self._run_task, spec, data, data_ref)
        self._active_futures[spec.task_id] = future
        future.add_done_callback(lambda f: self._on_task_done(spec, f))

    def _run_task(self, spec, data, data_ref):
        """Execute a single task — called in thread pool."""
        from .executor import TaskExecutor
        executor = TaskExecutor(worker=self)
        return executor.run(spec, data=data, data_ref=data_ref)

    def _on_task_done(self, spec, future) -> None:
        """Callback when a task completes or fails."""
        import httpx
        self._active_futures.pop(spec.task_id, None)
        try:
            result = future.result()
            self._completed += 1
            self._total_duration += result.get("duration_s", 0)
            # Post result to Dispatcher
            # Serialize result for JSON transport
            from stockstat._core.codec import CloudpickleCodec
            import base64
            result_bytes = CloudpickleCodec().encode(result["result"])
            result_b64 = base64.b64encode(result_bytes).decode("ascii")
            httpx.post(f"{self._url}/dispatch/complete", json={
                "worker_id": self._worker_id,
                "slice_id": spec.task_id,
                "result": result_b64,
                "result_codec": "cloudpickle",
            }, timeout=30)
        except Exception as e:
            self._failed += 1
            tb = traceback.format_exc()
            try:
                httpx.post(f"{self._url}/dispatch/fail", json={
                    "worker_id": self._worker_id,
                    "slice_id": spec.task_id,
                    "error": str(e),
                    "traceback": tb,
                    "retryable": True,
                }, timeout=10)
            except Exception:
                pass

    def _send_partial(self, slice_id: str, partial: dict) -> None:
        """Send a partial result to the Dispatcher (V2 §13.2)."""
        import httpx
        try:
            httpx.post(f"{self._url}/dispatch/partial", json={
                "worker_id": self._worker_id,
                "slice_id": slice_id,
                "partial": partial,
            }, timeout=5)
        except Exception:
            pass

    def _unregister(self) -> None:
        import httpx
        try:
            httpx.post(f"{self._url}/dispatch/unregister/{self._worker_id}", timeout=5)
        except Exception:
            pass

    def _avg_duration(self) -> float:
        return self._total_duration / self._completed if self._completed > 0 else 0


def _get_version() -> str:
    try:
        import stockstat
        return stockstat.__version__
    except Exception:
        return "unknown"


# Need base64 at module level
import base64
