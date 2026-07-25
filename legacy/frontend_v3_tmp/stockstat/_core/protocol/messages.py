"""Message type constants — V2 §12.4 message type table.

All inter-node messages share a single Envelope format, distinguished
by the ``type`` field. This module defines the canonical type strings
so callers don't pass mistyped strings.

Three categories (V2 §12.4):
- Control plane (Client <-> Dispatcher): light JSON
- Dispatch plane (Dispatcher <-> Worker): task assignment + results
- Data plane (large data transfer): Arrow IPC streams / refs

Adding a new message type requires only adding a constant here and a
handler on the receiving side; the Envelope format is unchanged.
"""
from __future__ import annotations


# ── Control plane: Client <-> Dispatcher ───────────────────────
# Light JSON messages for task submission, status, result, cancel.

TASK_SUBMIT = "task.submit"  # Client -> Dispatcher: submit TaskSpec
TASK_ACK = "task.ack"  # Dispatcher -> Client: confirm receipt
TASK_STATUS = "task.status"  # Client -> Dispatcher: query status
TASK_STATUS_REPLY = "task.status.reply"  # Dispatcher -> Client
TASK_RESULT = "task.result"  # Client -> Dispatcher: fetch result
TASK_RESULT_REPLY = "task.result.reply"  # Dispatcher -> Client
TASK_CANCEL = "task.cancel"  # Client -> Dispatcher: cancel task
TASK_PROGRESS = "task.progress"  # Dispatcher -> Client (push): progress
TASK_ERROR = "task.error"  # Dispatcher -> Client: error report

CLUSTER_INFO = "cluster.info"  # Client -> Dispatcher: query topology
CLUSTER_INFO_REPLY = "cluster.info.reply"  # Dispatcher -> Client

# ── Dispatch plane: Dispatcher <-> Worker ──────────────────────
# Task assignment, completion, failure, heartbeat, registration.

DISPATCH_ASSIGN = "dispatch.assign"  # Dispatcher -> Worker: assign slice
DISPATCH_ACK = "dispatch.ack"  # Worker -> Dispatcher: confirm receipt
DISPATCH_COMPLETE = "dispatch.complete"  # Worker -> Dispatcher: final result
DISPATCH_PARTIAL = "dispatch.partial"  # Worker -> Dispatcher: partial result (V2 §13.2)
DISPATCH_FAIL = "dispatch.fail"  # Worker -> Dispatcher: failure report
DISPATCH_HEARTBEAT = "dispatch.heartbeat"  # Worker -> Dispatcher: heartbeat
DISPATCH_REGISTER = "dispatch.register"  # Worker -> Dispatcher: register
DISPATCH_UNREGISTER = "dispatch.unregister"  # Worker -> Dispatcher: graceful exit
DISPATCH_DRAIN = "dispatch.drain"  # Dispatcher -> Worker: stop accepting (V2 §13.4)
DISPATCH_PREEMPT = "dispatch.preempt"  # Dispatcher -> Worker: pause (V2 §13.3)
DISPATCH_RESUME = "dispatch.resume"  # Dispatcher -> Worker: resume
DISPATCH_PREEMPT_REJECTED = "dispatch.preempt_rejected"  # Worker -> Dispatcher

# ── Data plane: large data transfer ────────────────────────────
# Arrow IPC streams / shared-memory refs / Storage URLs.

DATA_FETCH = "data.fetch"  # Dispatcher -> Storage: prefetch request
DATA_STREAM = "data.stream"  # Storage -> Dispatcher: data stream (Arrow)
DATA_REF = "data.ref"  # Dispatcher -> Worker: data reference

# ── Service discovery (V2 §13.4) ───────────────────────────────

CLUSTER_DISCOVER = "cluster.discover"  # Worker -> Storage: find dispatchers
CLUSTER_DISCOVER_REPLY = "cluster.discover.reply"  # Storage -> Worker


# ── Content type constants ─────────────────────────────────────
# Standard content types for Envelope.headers.content_type

CT_TASK_JSON = "application/vnd.stockstat.task+json"
CT_RESULT_ARROW = "application/vnd.stockstat.result+arrow"
CT_RESULT_PICKLE = "application/vnd.stockstat.result+cloudpickle"
CT_RESULT_JSON = "application/vnd.stockstat.result+json"
CT_JSON = "application/json"
CT_ARROW = "application/vnd.apache.arrow.file"
CT_PARQUET = "application/vnd.apache.parquet"
CT_CLOUDPICKLE = "application/vnd.python.cloudpickle"
CT_OCTET = "application/octet-stream"


# ── Message type -> HTTP path mapping (for HttpTransport) ──────
# Maps message types to REST endpoints so HttpTransport can route
# without inspecting payload.

TYPE_TO_PATH = {
    TASK_SUBMIT: "/dispatch/submit",
    TASK_STATUS: "/dispatch/status",
    TASK_RESULT: "/dispatch/result",
    TASK_CANCEL: "/dispatch/cancel",
    CLUSTER_INFO: "/dispatch/cluster",
    DISPATCH_REGISTER: "/dispatch/register",
    DISPATCH_HEARTBEAT: "/dispatch/heartbeat",
    DISPATCH_ASSIGN: "/dispatch/assign",
    DISPATCH_COMPLETE: "/dispatch/complete",
    DISPATCH_FAIL: "/dispatch/fail",
    DATA_FETCH: "/api/v1/ohlcv",
}


# ── Groupings for validation / dispatch ────────────────────────

CONTROL_TYPES = {
    TASK_SUBMIT, TASK_ACK, TASK_STATUS, TASK_STATUS_REPLY,
    TASK_RESULT, TASK_RESULT_REPLY, TASK_CANCEL, TASK_PROGRESS, TASK_ERROR,
    CLUSTER_INFO, CLUSTER_INFO_REPLY,
}

DISPATCH_TYPES = {
    DISPATCH_ASSIGN, DISPATCH_ACK, DISPATCH_COMPLETE, DISPATCH_PARTIAL,
    DISPATCH_FAIL, DISPATCH_HEARTBEAT, DISPATCH_REGISTER, DISPATCH_UNREGISTER,
    DISPATCH_DRAIN, DISPATCH_PREEMPT, DISPATCH_RESUME, DISPATCH_PREEMPT_REJECTED,
}

DATA_TYPES = {DATA_FETCH, DATA_STREAM, DATA_REF}

DISCOVERY_TYPES = {CLUSTER_DISCOVER, CLUSTER_DISCOVER_REPLY}

ALL_TYPES = CONTROL_TYPES | DISPATCH_TYPES | DATA_TYPES | DISCOVERY_TYPES


def is_control(t: str) -> bool:
    return t in CONTROL_TYPES


def is_dispatch(t: str) -> bool:
    return t in DISPATCH_TYPES


def is_data(t: str) -> bool:
    return t in DATA_TYPES
