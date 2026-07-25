"""PluginRegistry — 插件注册表。"""
from __future__ import annotations

from typing import Any, Optional


class PluginRegistry:
    """插件注册表 — Dispatcher / Admin / 自定义插件挂载点。"""

    def __init__(self):
        self._plugins: dict = {}

    def register(self, plugin: Any) -> None:
        name = getattr(plugin, "name", None) or str(id(plugin))
        self._plugins[name] = plugin

    def unregister(self, name: str) -> None:
        self._plugins.pop(name, None)

    def get(self, name: str) -> Optional[Any]:
        return self._plugins.get(name)

    def list(self) -> list:
        return list(self._plugins.keys())

    def mount_all(self, app: Any, **kwargs) -> None:
        """挂载所有已注册插件到 FastAPI app。"""
        for plugin in self._plugins.values():
            mount = getattr(plugin, "mount", None)
            if callable(mount):
                mount(app, **kwargs)

    def unmount_all(self, app: Any) -> None:
        for plugin in self._plugins.values():
            unmount = getattr(plugin, "unmount", None)
            if callable(unmount):
                unmount(app)

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins


__all__ = ["PluginRegistry"]
