"""test_workers.py — WorkerRegistry 测试 (25 项)。"""
from __future__ import annotations

import time

import pytest

from stockstat_dispatcher import WorkerRegistry, WorkerRecord


def make_reg_msg(worker_id="w1", alias="worker-1", concurrency=4,
                 capabilities=None, preemptable=False):
    return {
        "worker_id": worker_id,
        "alias": alias,
        "address": "192.168.1.1",
        "port": 9100,
        "concurrency": concurrency,
        "hardware": {"cpu": {"cores": 8}},
        "capabilities": capabilities or ["backtest", "indicator"],
        "stockstat_version": "3.1.0",
        "labels": {"zone": "east"},
        "preemptable": preemptable,
    }


class TestRegister:
    def test_register_returns_worker_id(self):
        reg = WorkerRegistry()
        wid = reg.register(make_reg_msg())
        assert wid == "w1"

    def test_register_generates_id_if_missing(self):
        reg = WorkerRegistry()
        msg = make_reg_msg()
        msg.pop("worker_id")
        wid = reg.register(msg)
        assert len(wid) > 0

    def test_register_creates_record(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg("w1", "alpha"))
        w = reg.get("w1")
        assert w is not None
        assert w.alias == "alpha"
        assert w.concurrency == 4
        assert w.status == "online"


class TestHeartbeat:
    def test_heartbeat_updates(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg())
        time.sleep(0.01)
        reg.update_heartbeat({"worker_id": "w1", "active_tasks": 2})
        w = reg.get("w1")
        assert w.active_tasks == 2

    def test_heartbeat_sets_busy_when_full(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg("w1", concurrency=2))
        reg.update_heartbeat({"worker_id": "w1", "active_tasks": 2})
        w = reg.get("w1")
        assert w.status == "busy"

    def test_heartbeat_unknown_worker_ignored(self):
        reg = WorkerRegistry()
        reg.update_heartbeat({"worker_id": "nonexistent"})

    def test_heartbeat_sets_online_when_freed(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg("w1", concurrency=2))
        reg.update_heartbeat({"worker_id": "w1", "active_tasks": 2})
        reg.update_heartbeat({"worker_id": "w1", "active_tasks": 1})
        w = reg.get("w1")
        assert w.status == "online"


class TestUnregister:
    def test_unregister_sets_offline(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg())
        reg.unregister("w1")
        w = reg.get("w1")
        assert w.status == "offline"

    def test_unregister_unknown(self):
        reg = WorkerRegistry()
        reg.unregister("nonexistent")  # 不应抛异常


class TestActiveTasks:
    def test_increment_active(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg(concurrency=2))
        reg.increment_active("w1")
        w = reg.get("w1")
        assert w.active_tasks == 1

    def test_increment_to_busy(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg(concurrency=1))
        reg.increment_active("w1")
        w = reg.get("w1")
        assert w.status == "busy"

    def test_decrement_active(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg(concurrency=2))
        reg.increment_active("w1")
        reg.decrement_active("w1")
        w = reg.get("w1")
        assert w.active_tasks == 0
        assert w.completed_tasks == 1

    def test_decrement_failed(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg())
        reg.increment_active("w1")
        reg.decrement_active("w1", completed=False, failed=True)
        w = reg.get("w1")
        assert w.failed_tasks == 1


class TestTimeout:
    def test_check_timeouts(self):
        reg = WorkerRegistry(offline_timeout=0.05)
        reg.register(make_reg_msg())
        time.sleep(0.1)
        timed_out = reg.check_timeouts()
        assert "w1" in timed_out
        assert reg.get("w1").status == "offline"

    def test_no_timeout_when_recent(self):
        reg = WorkerRegistry(offline_timeout=30.0)
        reg.register(make_reg_msg())
        reg.update_heartbeat({"worker_id": "w1"})
        timed_out = reg.check_timeouts()
        assert timed_out == []


class TestListWorkers:
    def test_list_excludes_offline(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg("w1"))
        reg.register(make_reg_msg("w2"))
        reg.unregister("w2")
        workers = reg.list_workers()
        ids = [w["worker_id"] for w in workers]
        assert "w1" in ids
        assert "w2" not in ids

    def test_list_include_offline(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg("w1"))
        reg.unregister("w1")
        workers = reg.list_workers(include_offline=True)
        assert len(workers) == 1

    def test_list_filter_labels(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg("w1", alias="a"))
        msg2 = make_reg_msg("w2")
        msg2["labels"] = {"zone": "west"}
        reg.register(msg2)
        workers = reg.list_workers(filter_labels={"zone": "east"})
        assert len(workers) == 1
        assert workers[0]["worker_id"] == "w1"

    def test_list_include_hardware(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg())
        workers = reg.list_workers(include_hardware=True)
        assert "hardware" in workers[0]

    def test_list_without_hardware(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg())
        workers = reg.list_workers(include_hardware=False)
        assert "hardware" not in workers


class TestStats:
    def test_empty_stats(self):
        reg = WorkerRegistry()
        s = reg.stats()
        assert s["total_workers"] == 0
        assert s["online_workers"] == 0

    def test_stats_after_register(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg("w1", concurrency=4))
        reg.register(make_reg_msg("w2", concurrency=2))
        s = reg.stats()
        assert s["total_workers"] == 2
        assert s["online_workers"] == 2
        assert s["total_concurrency"] == 6
        assert s["available_concurrency"] == 6

    def test_stats_with_active(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg(concurrency=4))
        reg.increment_active("w1")
        s = reg.stats()
        assert s["active_tasks"] == 1
        assert s["available_concurrency"] == 3

    def test_stats_with_offline(self):
        reg = WorkerRegistry()
        reg.register(make_reg_msg())
        reg.unregister("w1")
        s = reg.stats()
        assert s["online_workers"] == 0
        assert s["offline_workers"] == 1


class TestWorkerRecord:
    def test_record_fields(self):
        w = WorkerRecord(worker_id="w1", alias="alpha", concurrency=8)
        assert w.worker_id == "w1"
        assert w.alias == "alpha"
        assert w.concurrency == 8
        assert w.status == "online"
        assert w.capabilities == []
