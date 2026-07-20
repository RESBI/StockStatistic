"""Renderer plugins — register renderers to the PluginRegistry."""
from __future__ import annotations

from typing import Any, Optional


class RendererPlugin:
    """Plugin wrapper for a chart renderer."""
    category = "renderers"

    def __init__(self, name: str, renderer: Any, description: str = "") -> None:
        self.name = name
        self.version = "1.0"
        self.description = description
        self._renderer = renderer

    def initialize(self, context: Any) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health_check(self) -> bool:
        try:
            return self._renderer.available()
        except Exception:
            return False

    @property
    def renderer(self) -> Any:
        return self._renderer

    def render(self, spec: Any) -> Any:
        return self._renderer.render(spec)

    def savefig(self, path: str) -> None:
        self._renderer.savefig(path)


def register_default_renderers(registry: Any) -> int:
    """Register all built-in renderers to the registry.

    Registers NullRenderer (always) and MatplotlibRenderer (if
    matplotlib is available) under the ``renderers`` namespace.
    """
    from ...plot.base import NullRenderer
    from ...plot.matplotlib_backend import MatplotlibRenderer

    count = 0

    registry.register("renderers", "null",
        RendererPlugin("null", NullRenderer(), "No-op renderer (fallback)"))
    count += 1

    mpl = MatplotlibRenderer()
    if mpl.available():
        registry.register("renderers", "matplotlib",
            RendererPlugin("matplotlib", mpl, "Matplotlib renderer"))
        count += 1

    return count


def get_renderer(registry: Any, name: Optional[str] = None) -> Any:
    """Get a renderer by name, or auto-detect if name is None."""
    if name is not None:
        plugin = registry.get("renderers", name)
        if plugin is not None:
            return plugin.renderer
        return None

    # Auto-detect: prefer matplotlib > null
    for preferred in ["matplotlib", "null"]:
        plugin = registry.get("renderers", preferred)
        if plugin is not None and plugin.health_check():
            return plugin.renderer
    return None
