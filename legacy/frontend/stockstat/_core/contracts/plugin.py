"""Plugin protocol — the universal extension point."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PluginContext(Protocol):
    """Context handed to a plugin at initialization time.

    Provides access to the config, the plugin registry itself, and the
    event bus. Concrete implementations are built by the application
    bootstrap.
    """
    config: Any
    registry: Any
    events: Any


@runtime_checkable
class PluginMetadata(Protocol):
    """Static metadata describing a plugin."""
    name: str
    version: str
    category: str
    description: str


@runtime_checkable
class Plugin(Protocol):
    """Universal plugin protocol.

    Every extension point (data source, indicator, cost model, fill
    model, execution model, renderer, codec) ultimately satisfies this
    protocol. Sub-protocols (e.g. :class:`StorageBackend`) refine it
    with domain-specific methods.
    """
    name: str
    version: str
    category: str

    def initialize(self, context: PluginContext) -> None: ...
    def shutdown(self) -> None: ...
    def health_check(self) -> bool: ...
