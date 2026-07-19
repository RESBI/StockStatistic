"""Task queue implementations — Memory and Redis backends.

The queue holds TaskSpec objects waiting to be assigned to Workers.
Workers dequeue via Dispatcher.assign_task() (pull model).

Phase 1 (P2): MemoryTaskQueue (single-process Dispatcher)
Phase 5 (P5): RedisTaskQueue (multi-process, persistent)
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Optional, Protocol


class TaskQueue(Protocol):
    """Abstract task queue."""

    def enqueue(self, spec) -> None: ...
    def dequeue(self, block: bool = True, timeout: float = None) -> Optional[object]: ...
    def size(self) -> int: ...
    def clear(self) -> None: ...


class MemoryTaskQueue:
    """In-memory priority queue — Phase 1 default.

    Uses ``queue.PriorityQueue`` so high-priority tasks (priority < 0)
    are dequeued first. Thread-safe for single-process Dispatcher.
    """

    name = "memory"

    def __init__(self) -> None:
        # PriorityQueue items: (priority, timestamp, task_id, spec)
        # timestamp breaks ties so FIFO within same priority
        self._q: "queue.PriorityQueue" = queue.PriorityQueue()
        self._size = 0
        self._lock = threading.Lock()

    def enqueue(self, spec) -> None:
        priority = getattr(spec.dispatch_spec, "priority", 0)
        ts = time.time()
        with self._lock:
            self._q.put((priority, ts, spec.task_id, spec))
            self._size += 1

    def dequeue(self, block: bool = True, timeout: float = None) -> Optional[object]:
        try:
            if block:
                item = self._q.get(timeout=timeout)
            else:
                item = self._q.get_nowait()
            with self._lock:
                self._size -= 1
            # Return just the spec (drop priority/timestamp/ts)
            return item[3]
        except queue.Empty:
            return None

    def size(self) -> int:
        with self._lock:
            return self._size

    def clear(self) -> None:
        with self._lock:
            while not self._q.empty():
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
            self._size = 0


class RedisTaskQueue:
    """Redis-backed queue — Phase 5, multi-process Dispatcher.

    Uses Redis sorted sets (ZADD) for priority ordering and BRPOP for
    blocking dequeue. Requires ``redis`` package.

    The queue is split into:
    - A sorted set ``stockstat:tasks:pending`` (score = priority)
    - Per-task hash ``stockstat:task:{id}`` storing the serialized spec
    """

    name = "redis"

    def __init__(self, redis_url: str, queue_name: str = "stockstat:tasks") -> None:
        import redis
        self._r = redis.from_url(redis_url)
        self._queue_name = queue_name
        self._pending_key = f"{queue_name}:pending"
        self._task_prefix = f"{queue_name}:task"

    def enqueue(self, spec) -> None:
        import json
        priority = getattr(spec.dispatch_spec, "priority", 0)
        # Redis ZADD: lower score = higher priority (popped first)
        # Negate so priority=-1 (high) becomes score=1 (popped first)
        score = -priority
        self._r.hset(f"{self._task_prefix}:{spec.task_id}", "spec",
                      json.dumps(spec.to_dict()))
        self._r.zadd(self._pending_key, {spec.task_id: score})

    def dequeue(self, block: bool = True, timeout: float = None) -> Optional[object]:
        import json
        from stockstat._core.contracts.task import TaskSpec
        # Get the highest-priority task
        if block:
            # Use BZPOPMIN for blocking dequeue
            result = self._r.bzpopmin(self._pending_key, timeout=int(timeout or 0))
            if result is None:
                return None
            _, task_id_bytes, _ = result
            task_id = task_id_bytes.decode() if isinstance(task_id_bytes, bytes) else task_id_bytes
        else:
            result = self._r.zpopmin(self._pending_key, 1)
            if not result:
                return None
            task_id_bytes, _ = result[0]
            task_id = task_id_bytes.decode() if isinstance(task_id_bytes, bytes) else task_id_bytes
        # Fetch the spec
        spec_raw = self._r.hget(f"{self._task_prefix}:{task_id}", "spec")
        if spec_raw is None:
            return None
        if isinstance(spec_raw, bytes):
            spec_raw = spec_raw.decode("utf-8")
        spec_dict = json.loads(spec_raw)
        return TaskSpec.from_dict(spec_dict)

    def size(self) -> int:
        return self._r.zcard(self._pending_key)

    def clear(self) -> None:
        self._r.delete(self._pending_key)


def build_queue(backend: str = "memory", redis_url: str = None) -> TaskQueue:
    """Factory: build a queue by backend name."""
    if backend == "redis":
        if redis_url is None:
            raise ValueError("redis_url is required for Redis backend")
        return RedisTaskQueue(redis_url)
    if backend == "memory":
        return MemoryTaskQueue()
    raise ValueError(f"Unknown queue backend: {backend!r}")
