"""Compute backend implementations — V3 §8.

Three implementations of the :class:`ComputeBackend` protocol:

- :class:`LocalComputeBackend` (Phase 1, default): in-process direct call
- :class:`RemoteComputeBackend` (Phase 3+): via Transport to Dispatcher
- :class:`AutoComputeBackend` (Phase 3+): routes by task size

Phase 1 ships only LocalComputeBackend.
"""
from .local import LocalComputeBackend

__all__ = ["LocalComputeBackend"]
