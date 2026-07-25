"""Error classification for v2.0."""
from __future__ import annotations

from typing import Any, Optional


class AppError(Exception):
    """Base application error with error code and context.

    Attributes:
        code: Machine-readable error code (e.g. ``"DATA_NOT_FOUND"``).
        message: Human-readable message.
        context: Additional structured context.
        recoverable: Whether the caller may retry.
    """
    code: str = "INTERNAL_ERROR"
    recoverable: bool = False

    def __init__(
        self,
        message: str = "",
        code: Optional[str] = None,
        context: Optional[dict] = None,
        recoverable: Optional[bool] = None,
    ) -> None:
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


class DataNotFoundError(AppError):
    code = "DATA_NOT_FOUND"


class SymbolNotFoundError(AppError):
    code = "SYMBOL_NOT_FOUND"


class AdapterError(AppError):
    code = "ADAPTER_FAILED"
    recoverable = True


class InvalidParamsError(AppError):
    code = "INVALID_PARAMS"


class RateLimitedError(AppError):
    code = "RATE_LIMITED"
    recoverable = True


class LookaheadError(AppError):
    code = "LOOKAHEAD_VIOLATION"


class PluginNotFoundError(AppError):
    code = "PLUGIN_NOT_FOUND"


# ── V3 compute offload errors ─────────────────────────────────


class TaskError(AppError):
    """Task execution failed on the compute backend.

    Raised by ``TaskRef.wait()`` / ``TaskRef.result()`` when the
    underlying task entered the FAILED state. ``context`` includes
    ``task_id``, ``worker_id``, ``traceback`` (if available).
    """
    code = "TASK_FAILED"


class TaskNotReadyError(AppError):
    """Task has not yet completed; result cannot be fetched.

    Raised by ``TaskRef.result()`` (non-blocking) when the task is
    still PENDING or RUNNING. Caller should ``wait()`` or poll.
    """
    code = "TASK_NOT_READY"
    recoverable = True


class TaskCancelledError(AppError):
    """Task was cancelled (by client request or worker timeout)."""
    code = "TASK_CANCELLED"


class TaskTimeoutError(AppError):
    """Task did not complete within the allotted timeout."""
    code = "TASK_TIMEOUT"
    recoverable = True


class TaskNotFoundError(AppError):
    """Task ID not recognized by the backend (unknown or expired)."""
    code = "TASK_NOT_FOUND"


class ProtocolMismatchError(AppError):
    """Protocol version / codec negotiation failed between nodes.

    Raised when a Client declares ``accepted_codecs`` / ``accepted_encodings``
    that the Dispatcher cannot satisfy.
    """
    code = "PROTOCOL_MISMATCH"


class TransportError(AppError):
    """Underlying transport failure (network, connection, decode)."""
    code = "TRANSPORT_ERROR"
    recoverable = True


class DispatcherUnavailableError(AppError):
    """Dispatcher cannot be reached or has crashed."""
    code = "DISPATCHER_UNAVAILABLE"
    recoverable = True


class WorkerCapabilityError(AppError):
    """No available Worker supports the requested task_type."""
    code = "WORKER_CAPABILITY_INSUFFICIENT"
    recoverable = True
