"""Foundation 错误体系 — 12 个异常类。"""
from __future__ import annotations
from typing import Any, Optional


class AppError(Exception):
    """基础应用错误 — 携带 code + context + recoverable。"""
    code: str = "INTERNAL_ERROR"
    recoverable: bool = False

    def __init__(self, message: str = "", *, code: Optional[str] = None,
                 context: Optional[dict] = None, recoverable: Optional[bool] = None):
        self.message = message or self.code
        if code is not None:
            self.code = code
        self.context = context or {}
        if recoverable is not None:
            self.recoverable = recoverable
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "context": self.context,
            "recoverable": self.recoverable,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AppError":
        code = d.get("code", "INTERNAL_ERROR")
        for err_cls in _ALL_ERRORS:
            if err_cls.code == code:
                return err_cls(
                    d.get("message", ""),
                    code=code,
                    context=d.get("context", {}),
                    recoverable=d.get("recoverable"),
                )
        return cls(d.get("message", ""), code=code,
                   context=d.get("context", {}),
                   recoverable=d.get("recoverable"))


class TaskError(AppError):
    code = "TASK_FAILED"
    recoverable = False


class TaskNotReadyError(AppError):
    code = "TASK_NOT_READY"
    recoverable = True


class TaskCancelledError(AppError):
    code = "TASK_CANCELLED"
    recoverable = False


class TaskTimeoutError(AppError):
    code = "TASK_TIMEOUT"
    recoverable = True


class TaskNotFoundError(AppError):
    code = "TASK_NOT_FOUND"
    recoverable = False


class ProtocolMismatchError(AppError):
    code = "PROTOCOL_MISMATCH"
    recoverable = False


class TransportError(AppError):
    code = "TRANSPORT_ERROR"
    recoverable = True


class DispatcherUnavailableError(AppError):
    code = "DISPATCHER_UNAVAILABLE"
    recoverable = True


class WorkerCapabilityError(AppError):
    code = "WORKER_CAPABILITY_INSUFFICIENT"
    recoverable = True


class StorageError(AppError):
    code = "STORAGE_ERROR"
    recoverable = True


class ComputeError(AppError):
    code = "COMPUTE_FAILED"
    recoverable = False


class ConfigError(AppError):
    code = "CONFIG_ERROR"
    recoverable = False


_ALL_ERRORS = [
    AppError, TaskError, TaskNotReadyError, TaskCancelledError,
    TaskTimeoutError, TaskNotFoundError, ProtocolMismatchError,
    TransportError, DispatcherUnavailableError, WorkerCapabilityError,
    StorageError, ComputeError, ConfigError,
]


__all__ = [
    "AppError", "TaskError", "TaskNotReadyError", "TaskCancelledError",
    "TaskTimeoutError", "TaskNotFoundError", "ProtocolMismatchError",
    "TransportError", "DispatcherUnavailableError", "WorkerCapabilityError",
    "StorageError", "ComputeError", "ConfigError",
]
