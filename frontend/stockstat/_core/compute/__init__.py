"""Compute backend implementations — V3 §8.

Three implementations of the ComputeBackend protocol:
- LocalComputeBackend (P1, default): in-process direct call
- RemoteComputeBackend (P3): via Transport to Dispatcher
- AutoComputeBackend (P3): routes by task size / type
"""
from .local import LocalComputeBackend
from .remote import RemoteComputeBackend
from .auto import AutoComputeBackend

__all__ = ["LocalComputeBackend", "RemoteComputeBackend", "AutoComputeBackend"]
