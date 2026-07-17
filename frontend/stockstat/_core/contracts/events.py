"""Event protocol — pub/sub for the event-driven core."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class Event:
    """An immutable event flowing through the bus.

    Attributes:
        topic: Hierarchical topic path (e.g. ``"data.ohlcv"``).
        payload: The event data (any picklable object).
        timestamp: UTC timestamp when the event was created.
        source: Identifier of the producer (e.g. ``"binance"``,
            ``"replay"``, ``"backtest"``).
    """
    topic: str
    payload: Any
    timestamp: Any  # pd.Timestamp
    source: str = ""


@runtime_checkable
class EventSubscriber(Protocol):
    """A subscriber that handles events for specific topics."""
    def handle(self, event: Event) -> None: ...
    def topics(self) -> list[str]: ...


@runtime_checkable
class EventPublisher(Protocol):
    """A publisher that can emit events onto a bus."""
    def publish(self, topic: str, payload: Any, source: str = "") -> None: ...
