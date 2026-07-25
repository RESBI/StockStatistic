"""test_queue.py — TaskQueue 测试 (20 项)。"""
from __future__ import annotations

import pytest

from stockstat_foundation import TaskSpec, DataSpec, ComputeSpec, DispatchSpec
from stockstat_dispatcher import MemoryTaskQueue, build_queue


def make_spec(task_id="t1", priority=0, task_type="backtest"):
    return TaskSpec(
        task_id=task_id,
        data_spec=DataSpec(symbols=["BTC"]),
        compute_spec=ComputeSpec(task_type=task_type),
        dispatch_spec=DispatchSpec(priority=priority),
    )


class TestMemoryTaskQueue:
    def test_enqueue_dequeue(self):
        q = MemoryTaskQueue()
        spec = make_spec()
        q.enqueue(spec)
        assert q.size() == 1
        result = q.dequeue()
        assert result is not None
        assert result.task_id == "t1"
        assert q.size() == 0

    def test_dequeue_empty_returns_none(self):
        q = MemoryTaskQueue()
        assert q.dequeue() is None

    def test_dequeue_non_block(self):
        q = MemoryTaskQueue()
        q.enqueue(make_spec())
        result = q.dequeue(block=False)
        assert result is not None

    def test_priority_ordering(self):
        q = MemoryTaskQueue()
        # priority 越小越优先
        q.enqueue(make_spec("low", priority=1))
        q.enqueue(make_spec("high", priority=-1))
        q.enqueue(make_spec("normal", priority=0))
        first = q.dequeue()
        second = q.dequeue()
        third = q.dequeue()
        assert first.task_id == "high"
        assert second.task_id == "normal"
        assert third.task_id == "low"

    def test_size(self):
        q = MemoryTaskQueue()
        for i in range(5):
            q.enqueue(make_spec(f"t{i}"))
        assert q.size() == 5

    def test_clear(self):
        q = MemoryTaskQueue()
        q.enqueue(make_spec())
        q.enqueue(make_spec("t2"))
        q.clear()
        assert q.size() == 0

    def test_multiple_enqueue_dequeue(self):
        q = MemoryTaskQueue()
        for i in range(10):
            q.enqueue(make_spec(f"t{i}"))
        for i in range(10):
            assert q.dequeue() is not None
        assert q.size() == 0

    def test_name(self):
        assert MemoryTaskQueue().name == "memory"


class TestBuildQueue:
    def test_default_memory(self):
        q = build_queue()
        assert isinstance(q, MemoryTaskQueue)

    def test_memory_explicit(self):
        q = build_queue("memory")
        assert isinstance(q, MemoryTaskQueue)

    def test_redis_without_url_raises(self):
        with pytest.raises(ValueError):
            build_queue("redis")

    def test_redis_with_url(self):
        try:
            import redis  # noqa: F401
        except ImportError:
            with pytest.raises(ImportError):
                build_queue("redis", "redis://localhost:6379/0")
            return
        from stockstat_dispatcher import RedisTaskQueue
        q = build_queue("redis", "redis://localhost:6379/0")
        assert isinstance(q, RedisTaskQueue)

    def test_unknown_backend_defaults_memory(self):
        q = build_queue("unknown")
        assert isinstance(q, MemoryTaskQueue)


class TestRedisTaskQueueSkipped:
    def test_redis_import_error(self):
        try:
            import redis  # noqa: F401
            pytest.skip("redis installed")
        except ImportError:
            from stockstat_dispatcher import RedisTaskQueue
            with pytest.raises(ImportError, match="redis"):
                RedisTaskQueue("redis://localhost:6379/0")


class TestQueueProtocolConformance:
    def test_queue_has_methods(self):
        q = MemoryTaskQueue()
        for m in ["enqueue", "dequeue", "size", "clear"]:
            assert hasattr(q, m)

    def test_enqueue_returns_none(self):
        q = MemoryTaskQueue()
        assert q.enqueue(make_spec()) is None

    def test_dequeue_returns_spec_or_none(self):
        q = MemoryTaskQueue()
        assert q.dequeue() is None
        q.enqueue(make_spec())
        result = q.dequeue()
        assert isinstance(result, TaskSpec)

    def test_fifo_within_same_priority(self):
        q = MemoryTaskQueue()
        q.enqueue(make_spec("first"))
        q.enqueue(make_spec("second"))
        assert q.dequeue().task_id == "first"
        assert q.dequeue().task_id == "second"

    def test_clear_empty_queue(self):
        q = MemoryTaskQueue()
        q.clear()
        assert q.size() == 0
