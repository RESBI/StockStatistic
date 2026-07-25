"""Protocol contracts for cross-layer communication.

All protocols are :class:`typing.Protocol` (structural subtyping). No
runtime registration is required to *implement* a protocol; any object
with the right methods qualifies. The :mod:`stockstat._core.plugin`
registry handles *discovery* and *lifecycle* of concrete implementations.
"""
from .plugin import Plugin, PluginContext, PluginMetadata
from .storage import StorageBackend, DataSchema, FieldDef
from .cache import CacheBackend
from .codec import Codec
from .renderer import Renderer
from .events import Event, EventSubscriber, EventPublisher
from .compute import ComputeBackend, TaskRef, TaskInfo, TaskState
from .task import TaskSpec, DataSpec, ComputeSpec, DispatchSpec
from .transport import Transport

__all__ = [
    "Plugin", "PluginContext", "PluginMetadata",
    "StorageBackend", "DataSchema", "FieldDef",
    "CacheBackend",
    "Codec",
    "Renderer",
    "Event", "EventSubscriber", "EventPublisher",
    # V3 compute offload contracts
    "ComputeBackend", "TaskRef", "TaskInfo", "TaskState",
    "TaskSpec", "DataSpec", "ComputeSpec", "DispatchSpec",
    "Transport",
]
