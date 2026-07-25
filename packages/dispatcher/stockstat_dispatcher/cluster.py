"""多级 Dispatcher 拓扑（骨架，P8 完整实现）。"""
from __future__ import annotations

from typing import Optional


class ClusterManager:
    """多级 Dispatcher 拓扑管理。"""

    def __init__(self, dispatcher):
        self._dispatcher = dispatcher

    def register_sub_dispatcher(self, msg: dict) -> dict:
        sub_id = msg.get("sub_id") or msg.get("id")
        if not sub_id:
            return {"status": "error", "error": "sub_id required"}
        self._dispatcher._sub_dispatchers[sub_id] = {
            "id": sub_id,
            "alias": msg.get("alias", sub_id),
            "address": msg.get("address", ""),
            "parent_url": msg.get("parent_url"),
            "status": "online",
            "worker_count": msg.get("worker_count", 0),
            "total_concurrency": msg.get("total_concurrency", 0),
        }
        return {"status": "registered", "sub_id": sub_id}

    def unregister_sub_dispatcher(self, sub_id: str) -> dict:
        if sub_id in self._dispatcher._sub_dispatchers:
            self._dispatcher._sub_dispatchers[sub_id]["status"] = "offline"
        return {"status": "unregistered"}

    def list_sub_dispatchers(self) -> list:
        return list(self._dispatcher._sub_dispatchers.values())


__all__ = ["ClusterManager"]
