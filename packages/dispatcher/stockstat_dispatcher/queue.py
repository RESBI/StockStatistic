"""TaskQueue — 任务队列（Memory / Redis）。"""
from __future__ import annotations

import queue
from typing import Optional

from stockstat_foundation import TaskSpec


class MemoryTaskQueue:
    """进程内队列 — queue.PriorityQueue + 优先级支持。"""
    name = "memory"

    def __init__(self):
        self._queue = queue.PriorityQueue()
        self._counter = 0

    def enqueue(self, spec: TaskSpec) -> None:
        priority = spec.dispatch_spec.priority
        self._counter += 1
        self._queue.put((priority, self._counter, spec))

    def dequeue(self, block: bool = False, timeout: Optional[float] = None):
        try:
            _, _, spec = self._queue.get(block=block, timeout=timeout)
            return spec
        except queue.Empty:
            return None

    def size(self) -> int:
        return self._queue.qsize()

    def clear(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


class RedisTaskQueue:
    """Redis 队列 — 跨进程持久化 + 优先级。"""
    name = "redis"

    def __init__(self, redis_url: str, queue_key: str = "stockstat:tasks"):
        try:
            import redis
        except ImportError as e:
            raise ImportError(
                "RedisTaskQueue requires 'redis'. "
                "Install with: pip install stockstat-dispatcher[redis]"
            ) from e
        self._r = redis.from_url(redis_url)
        self._queue_key = queue_key
        self._high_key = f"{queue_key}:high"
        self._normal_key = f"{queue_key}:normal"
        self._low_key = f"{queue_key}:low"

    def enqueue(self, spec: TaskSpec) -> None:
        from stockstat_foundation.codec import JsonCodec
        data = JsonCodec().encode(spec.to_dict())
        priority = spec.dispatch_spec.priority
        if priority < 0:
            self._r.lpush(self._high_key, data)
        elif priority > 0:
            self._r.lpush(self._low_key, data)
        else:
            self._r.lpush(self._normal_key, data)

    def dequeue(self, block: bool = False, timeout: Optional[float] = None):
        from stockstat_foundation.codec import JsonCodec
        for key in [self._high_key, self._normal_key, self._low_key]:
            data = self._r.rpop(key)
            if data is not None:
                return TaskSpec.from_dict(JsonCodec().decode(data))
        if block:
            result = self._r.brpop(
                [self._high_key, self._normal_key, self._low_key],
                timeout=int(timeout or 0),
            )
            if result:
                _, data = result
                return TaskSpec.from_dict(JsonCodec().decode(data))
        return None

    def size(self) -> int:
        return sum(self._r.llen(k) for k in
                   [self._high_key, self._normal_key, self._low_key])

    def clear(self) -> None:
        for k in [self._high_key, self._normal_key, self._low_key]:
            self._r.delete(k)


def build_queue(backend: str = "memory", redis_url: str = None):
    """工厂函数。"""
    if backend == "redis":
        if not redis_url:
            raise ValueError("redis_url required for redis queue")
        return RedisTaskQueue(redis_url)
    return MemoryTaskQueue()


__all__ = ["MemoryTaskQueue", "RedisTaskQueue", "build_queue"]
