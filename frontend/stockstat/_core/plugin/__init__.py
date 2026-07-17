"""Plugin registry — central discovery and lifecycle management."""
from __future__ import annotations

from typing import Any, Optional

from ..contracts import Plugin, PluginContext


class PluginRegistry:
    """Central registry for all plugin-based extensions.

    Plugins are organized into **namespaces** (e.g. ``"sources"``,
    ``"indicators"``, ``"cost_models"``). Within a namespace, each
    plugin has a unique name. The registry supports:

    * Explicit registration via :meth:`register`
    * Namespace-scoped lookup via :meth:`get`
    * Listing via :meth:`list`
    * Lifecycle management (``initialize`` / ``health_check`` /
      ``shutdown``)

    Automatic discovery via setuptools ``entry_points`` is supported
    through :meth:`discover` but requires plugins to be installed as
    packages with the ``stockstat.plugins`` entry-point group.
    """

    def __init__(self) -> None:
        # namespace -> {name -> plugin instance}
        self._plugins: dict[str, dict[str, Any]] = {}
        self._initialized: bool = False
        self._context: Optional[PluginContext] = None

    # ── Registration ──────────────────────────────────────────

    def register(self, namespace: str, name: str, plugin: Any) -> Any:
        """Register a plugin under ``namespace`` / ``name``.

        If the registry has already been bootstrapped (``initialize``
        called), the plugin is initialized immediately.

        Returns the plugin (for decorator-style use).
        """
        ns = self._plugins.setdefault(namespace, {})
        if name in ns:
            raise ValueError(
                f"Plugin '{name}' already registered in namespace '{namespace}'"
            )
        ns[name] = plugin
        if self._initialized and hasattr(plugin, "initialize"):
            plugin.initialize(self._context)
        return plugin

    def unregister(self, namespace: str, name: str) -> Optional[Any]:
        """Remove and return a plugin. Calls ``shutdown`` if initialized."""
        ns = self._plugins.get(namespace)
        if ns is None or name not in ns:
            return None
        plugin = ns.pop(name)
        if self._initialized and hasattr(plugin, "shutdown"):
            plugin.shutdown()
        return plugin

    # ── Lookup ────────────────────────────────────────────────

    def get(self, namespace: str, name: str) -> Optional[Any]:
        """Look up a plugin by namespace and name."""
        ns = self._plugins.get(namespace)
        if ns is None:
            return None
        return ns.get(name)

    def require(self, namespace: str, name: str) -> Any:
        """Like :meth:`get` but raises if not found."""
        plugin = self.get(namespace, name)
        if plugin is None:
            raise KeyError(
                f"No plugin '{name}' in namespace '{namespace}'. "
                f"Available: {list(self._plugins.get(namespace, {}).keys())}"
            )
        return plugin

    def list(self, namespace: Optional[str] = None) -> list[dict]:
        """List registered plugins.

        If ``namespace`` is given, list only that namespace; otherwise
        list all. Returns a list of ``{namespace, name, plugin}`` dicts.
        """
        result = []
        if namespace is not None:
            ns = self._plugins.get(namespace, {})
            for name, plugin in ns.items():
                result.append({"namespace": namespace, "name": name,
                               "plugin": plugin})
        else:
            for ns_name, ns in self._plugins.items():
                for name, plugin in ns.items():
                    result.append({"namespace": ns_name, "name": name,
                                   "plugin": plugin})
        return result

    def namespaces(self) -> list[str]:
        """Return all registered namespace names."""
        return list(self._plugins.keys())

    # ── Discovery ─────────────────────────────────────────────

    def discover(self) -> int:
        """Discover plugins via setuptools entry_points.

        Entry-point group: ``stockstat.plugins``. Each entry point
        should resolve to a callable that accepts the registry and
        registers plugins.

        Returns the number of entry points found.
        """
        try:
            from importlib.metadata import entry_points
        except ImportError:
            from importlib_metadata import entry_points  # type: ignore

        try:
            eps = entry_points(group="stockstat.plugins")
        except TypeError:
            # Python 3.9 compatibility
            eps = entry_points().get("stockstat.plugins", [])

        count = 0
        for ep in eps:
            try:
                func = ep.load()
                func(self)
                count += 1
            except Exception:
                pass  # silently skip broken plugins
        return count

    # ── Lifecycle ─────────────────────────────────────────────

    def initialize(self, context: PluginContext) -> None:
        """Initialize all registered plugins with a context."""
        self._context = context
        for ns in self._plugins.values():
            for plugin in ns.values():
                if hasattr(plugin, "initialize"):
                    plugin.initialize(context)
        self._initialized = True

    def health_check(self) -> dict[str, bool]:
        """Run health_check on all plugins. Returns ``{namespace.name: bool}``."""
        result = {}
        for ns_name, ns in self._plugins.items():
            for name, plugin in ns.items():
                if hasattr(plugin, "health_check"):
                    try:
                        result[f"{ns_name}.{name}"] = plugin.health_check()
                    except Exception:
                        result[f"{ns_name}.{name}"] = False
        return result

    def shutdown(self) -> None:
        """Shutdown all plugins in reverse registration order."""
        for ns in reversed(list(self._plugins.values())):
            for plugin in reversed(list(ns.values())):
                if hasattr(plugin, "shutdown"):
                    try:
                        plugin.shutdown()
                    except Exception:
                        pass
        self._initialized = False


# Module-level singleton
_registry: Optional[PluginRegistry] = None


def get_registry() -> PluginRegistry:
    """Return the global plugin registry singleton."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    if _registry is not None:
        _registry.shutdown()
    _registry = None
