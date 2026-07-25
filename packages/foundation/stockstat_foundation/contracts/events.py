"""Event Protocol — 事件订阅（预留）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class Event:
    """事件对象。"""
    type: str
    payload: Any = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: Optional[str] = None
    trace_id: Optional[str] = None


@runtime_checkable
class EventSubscriber(Protocol):
    """事件订阅者协议。"""
    def on_event(self, event: Event) -> None: ...
    def subscribe(self, event_type: str) -> None: ...
    def unsubscribe(self, event_type: str) -> None: ...


__all__ = ["Event", "EventSubscriber"]
