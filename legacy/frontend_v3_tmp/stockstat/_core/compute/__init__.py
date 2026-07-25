"""Compute backend implementations — V3 §8.

Three implementations of the ComputeBackend protocol:
- LocalComputeBackend (P1, default): in-process direct call
- RemoteComputeBackend (P3): via Transport to Dispatcher
- AutoComputeBackend (P3): routes by task size / type

Also exports the shared handler registry and Stream class for
incremental data processing (P4).
"""
from .local import LocalComputeBackend
from .remote import RemoteComputeBackend
from .auto import AutoComputeBackend
from .handlers import (
    Stream, dispatch, deserialize_strategy, encode_strategy,
    resolve_cost_model, resolve_fill_model, resolve_execution_model,
    serialize_result, deserialize_result, is_stream_aware,
    HANDLERS,
)
from .data_dispatch import (
    choose_data_dispatch, estimate_data_size, resolve_data_dispatch,
    SMALL_DATA_THRESHOLD, LARGE_DATA_THRESHOLD,
)

__all__ = [
    "LocalComputeBackend", "RemoteComputeBackend", "AutoComputeBackend",
    "Stream", "dispatch", "deserialize_strategy", "encode_strategy",
    "resolve_cost_model", "resolve_fill_model", "resolve_execution_model",
    "serialize_result", "deserialize_result", "is_stream_aware", "HANDLERS",
    "choose_data_dispatch", "estimate_data_size", "resolve_data_dispatch",
    "SMALL_DATA_THRESHOLD", "LARGE_DATA_THRESHOLD",
]
