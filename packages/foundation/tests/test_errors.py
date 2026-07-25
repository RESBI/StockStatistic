"""test_errors.py — 12 个异常类 / to_dict / 继承 (15 项)。"""
from __future__ import annotations

import pytest

from stockstat_foundation.errors import (
    AppError, TaskError, TaskNotReadyError, TaskCancelledError,
    TaskTimeoutError, TaskNotFoundError, ProtocolMismatchError,
    TransportError, DispatcherUnavailableError, WorkerCapabilityError,
    StorageError, ComputeError, ConfigError,
)


class TestAppError:
    def test_default(self):
        err = AppError("something wrong")
        assert err.message == "something wrong"
        assert err.code == "INTERNAL_ERROR"
        assert err.recoverable is False
        assert err.context == {}

    def test_custom_code_and_context(self):
        err = AppError("msg", code="CUSTOM", context={"k": "v"}, recoverable=True)
        assert err.code == "CUSTOM"
        assert err.context == {"k": "v"}
        assert err.recoverable is True

    def test_to_dict(self):
        err = AppError("msg", code="X", context={"a": 1}, recoverable=True)
        d = err.to_dict()
        assert d["code"] == "X"
        assert d["message"] == "msg"
        assert d["context"] == {"a": 1}
        assert d["recoverable"] is True

    def test_from_dict_roundtrip(self):
        err = TaskError("backtest failed", context={"task_type": "backtest"})
        d = err.to_dict()
        restored = AppError.from_dict(d)
        assert restored.code == "TASK_FAILED"
        assert restored.message == "backtest failed"
        assert restored.context["task_type"] == "backtest"


class TestExceptionHierarchy:
    def test_all_inherit_app_error(self):
        for cls in [TaskError, TaskNotReadyError, TaskCancelledError,
                    TaskTimeoutError, TaskNotFoundError, ProtocolMismatchError,
                    TransportError, DispatcherUnavailableError, WorkerCapabilityError,
                    StorageError, ComputeError, ConfigError]:
            assert issubclass(cls, AppError)
            assert issubclass(cls, Exception)

    def test_each_has_unique_code(self):
        codes = [
            TaskError.code, TaskNotReadyError.code, TaskCancelledError.code,
            TaskTimeoutError.code, TaskNotFoundError.code, ProtocolMismatchError.code,
            TransportError.code, DispatcherUnavailableError.code,
            WorkerCapabilityError.code, StorageError.code, ComputeError.code,
            ConfigError.code, AppError.code,
        ]
        assert len(set(codes)) == 13

    def test_task_error_code(self):
        assert TaskError.code == "TASK_FAILED"
        assert TaskError.recoverable is False

    def test_task_not_ready_recoverable(self):
        assert TaskNotReadyError.recoverable is True
        assert TaskNotReadyError.code == "TASK_NOT_READY"

    def test_task_cancelled_code(self):
        assert TaskCancelledError.code == "TASK_CANCELLED"

    def test_task_timeout_recoverable(self):
        assert TaskTimeoutError.recoverable is True

    def test_task_not_found(self):
        assert TaskNotFoundError.code == "TASK_NOT_FOUND"

    def test_protocol_mismatch(self):
        assert ProtocolMismatchError.recoverable is False

    def test_transport_recoverable(self):
        assert TransportError.recoverable is True

    def test_dispatcher_unavailable(self):
        assert DispatcherUnavailableError.recoverable is True

    def test_worker_capability(self):
        assert WorkerCapabilityError.code == "WORKER_CAPABILITY_INSUFFICIENT"

    def test_storage_error(self):
        assert StorageError.code == "STORAGE_ERROR"
