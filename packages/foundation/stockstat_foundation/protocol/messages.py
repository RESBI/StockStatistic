"""消息类型常量 + TYPE_TO_PATH 映射。"""
from __future__ import annotations

# Control plane (Client <-> Dispatcher)
TASK_SUBMIT = "task.submit"
TASK_ACK = "task.ack"
TASK_STATUS = "task.status"
TASK_STATUS_REPLY = "task.status.reply"
TASK_RESULT = "task.result"
TASK_RESULT_REPLY = "task.result.reply"
TASK_CANCEL = "task.cancel"
TASK_PROGRESS = "task.progress"
TASK_ERROR = "task.error"
CLUSTER_INFO = "cluster.info"
CLUSTER_INFO_REPLY = "cluster.info.reply"

# Dispatch plane (Dispatcher <-> Worker)
DISPATCH_ASSIGN = "dispatch.assign"
DISPATCH_ACK = "dispatch.ack"
DISPATCH_COMPLETE = "dispatch.complete"
DISPATCH_PARTIAL = "dispatch.partial"
DISPATCH_FAIL = "dispatch.fail"
DISPATCH_HEARTBEAT = "dispatch.heartbeat"
DISPATCH_REGISTER = "dispatch.register"
DISPATCH_UNREGISTER = "dispatch.unregister"
DISPATCH_DRAIN = "dispatch.drain"
DISPATCH_PREEMPT = "dispatch.preempt"
DISPATCH_RESUME = "dispatch.resume"
DISPATCH_PREEMPT_REJECTED = "dispatch.preempt_rejected"

# Data plane
DATA_FETCH = "data.fetch"
DATA_STREAM = "data.stream"
DATA_REF = "data.ref"

# Service discovery
CLUSTER_DISCOVER = "cluster.discover"
CLUSTER_DISCOVER_REPLY = "cluster.discover.reply"


TYPE_TO_PATH = {
    TASK_SUBMIT: "/dispatch/submit",
    TASK_STATUS: "/dispatch/status",
    TASK_RESULT: "/dispatch/result",
    TASK_CANCEL: "/dispatch/cancel",
    CLUSTER_INFO: "/dispatch/cluster",
    DISPATCH_REGISTER: "/dispatch/register",
    DISPATCH_HEARTBEAT: "/dispatch/heartbeat",
    DISPATCH_UNREGISTER: "/dispatch/unregister",
    DISPATCH_ASSIGN: "/dispatch/assign",
    DISPATCH_COMPLETE: "/dispatch/complete",
    DISPATCH_FAIL: "/dispatch/fail",
    DISPATCH_PARTIAL: "/dispatch/partial",
    DISPATCH_PREEMPT: "/dispatch/preempt",
    DISPATCH_RESUME: "/dispatch/resume",
    DISPATCH_DRAIN: "/dispatch/drain",
    CLUSTER_DISCOVER: "/dispatch/discover",
    DATA_FETCH: "/api/v1/ohlcv",
}


CONTROL_TYPES = {
    TASK_SUBMIT, TASK_ACK, TASK_STATUS, TASK_STATUS_REPLY,
    TASK_RESULT, TASK_RESULT_REPLY, TASK_CANCEL, TASK_PROGRESS,
    TASK_ERROR, CLUSTER_INFO, CLUSTER_INFO_REPLY,
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


__all__ = [
    "TASK_SUBMIT", "TASK_ACK", "TASK_STATUS", "TASK_STATUS_REPLY",
    "TASK_RESULT", "TASK_RESULT_REPLY", "TASK_CANCEL", "TASK_PROGRESS", "TASK_ERROR",
    "CLUSTER_INFO", "CLUSTER_INFO_REPLY",
    "DISPATCH_ASSIGN", "DISPATCH_ACK", "DISPATCH_COMPLETE", "DISPATCH_PARTIAL",
    "DISPATCH_FAIL", "DISPATCH_HEARTBEAT", "DISPATCH_REGISTER", "DISPATCH_UNREGISTER",
    "DISPATCH_DRAIN", "DISPATCH_PREEMPT", "DISPATCH_RESUME", "DISPATCH_PREEMPT_REJECTED",
    "DATA_FETCH", "DATA_STREAM", "DATA_REF",
    "CLUSTER_DISCOVER", "CLUSTER_DISCOVER_REPLY",
    "TYPE_TO_PATH", "CONTROL_TYPES", "DISPATCH_TYPES", "DATA_TYPES",
    "DISCOVERY_TYPES", "ALL_TYPES", "is_control", "is_dispatch", "is_data",
]
