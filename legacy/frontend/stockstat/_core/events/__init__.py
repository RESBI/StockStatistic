"""Event bus — in-process pub/sub for event-driven architecture."""
from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd

from ..contracts.events import Event, EventSubscriber


class EventBus:
    """In-process event bus with topic-based routing.

    Topics are hierarchical dot-separated paths (e.g.
    ``"data.ohlcv"``). A subscriber to ``"data"`` receives events
    published to ``"data.ohlcv"`` and ``"data.quote"``.

    The bus supports both synchronous dispatch (default) and is
    designed to be the unifying abstraction for:

    * **Backtesting**: :class:`EventReplay` publishes historical bars
    * **Real-time**: data sources publish live ticks
    * **Inter-component**: backtest engine publishes order/fill events
    """

    def __init__(self) -> None:
        # topic -> list of subscribers
        self._subscribers: dict[str, list[EventSubscriber]] = {}
        self._handlers: dict[str, list[Callable[[Event], None]]] = {}
        self._event_log: list[Event] = []
        self._logging: bool = False

    def subscribe(self, topic: str, subscriber: EventSubscriber) -> None:
        """Subscribe a subscriber to a topic."""
        self._subscribers.setdefault(topic, []).append(subscriber)

    def subscribe_handler(self, topic: str, handler: Callable[[Event], None]) -> None:
        """Subscribe a plain callable to a topic."""
        self._handlers.setdefault(topic, []).append(handler)

    def unsubscribe(self, topic: str, subscriber: EventSubscriber) -> None:
        """Remove a subscriber from a topic."""
        subs = self._subscribers.get(topic, [])
        if subscriber in subs:
            subs.remove(subscriber)

    def publish(self, topic: str, payload: Any, source: str = "") -> None:
        """Publish an event to a topic.

        The event is delivered to:

        * All subscribers of the exact topic
        * All subscribers of parent topics (e.g. ``"data"`` gets
          ``"data.ohlcv"`` events)
        * All handlers registered for matching topics
        """
        event = Event(
            topic=topic,
            payload=payload,
            timestamp=pd.Timestamp.utcnow(),
            source=source,
        )

        if self._logging:
            self._event_log.append(event)

        # Deliver to subscribers (exact + parent topics)
        for t, subs in self._subscribers.items():
            if topic == t or topic.startswith(t + "."):
                for sub in subs:
                    try:
                        sub.handle(event)
                    except Exception:
                        pass  # swallow to prevent cascade

        # Deliver to handlers
        for t, handlers in self._handlers.items():
            if topic == t or topic.startswith(t + "."):
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception:
                        pass

    def enable_logging(self) -> None:
        """Start recording all published events."""
        self._logging = True
        self._event_log.clear()

    def disable_logging(self) -> None:
        """Stop recording events."""
        self._logging = False

    def get_log(self) -> list[Event]:
        """Return the recorded event log (if logging enabled)."""
        return list(self._event_log)

    def clear(self) -> None:
        """Remove all subscribers and clear the log."""
        self._subscribers.clear()
        self._handlers.clear()
        self._event_log.clear()


class EventReplay:
    """Replay historical data as events.

    This is the bridge between storage and the event-driven engine.
    Given a DataFrame of historical bars, it publishes them as events
    in chronological order.
    """

    def __init__(self, bus: EventBus, topic: str = "data.ohlcv") -> None:
        self._bus = bus
        self._topic = topic

    def replay(
        self,
        data: pd.DataFrame,
        symbol: str = "",
        source: str = "replay",
        speed: Optional[float] = None,
    ) -> int:
        """Replay a DataFrame of bars as events.

        Args:
            data: DataFrame with a DatetimeIndex.
            symbol: Symbol to attach as payload metadata.
            source: Event source identifier.
            speed: If given, sleep between events (``1.0`` = real-time).
                ``None`` = instant replay (default, for backtesting).

        Returns:
            Number of events published.
        """
        import time

        count = 0
        for ts, row in data.iterrows():
            payload = {"symbol": symbol, "ts": ts, "bar": row}
            self._bus.publish(self._topic, payload, source=source)
            count += 1
            if speed is not None:
                # Approximate real-time pacing
                time.sleep(1.0 / speed)
        return count

    def replay_group(
        self,
        data: dict[str, dict[str, pd.DataFrame]],
        source: str = "replay",
    ) -> int:
        """Replay a multi-symbol multi-tf data group.

        ``data`` is ``{symbol: {tf: df}}``. Bars are merged into a
        single timeline by timestamp (finest tf drives the master
        index); coarser tfs are ffill-aligned.
        """
        # Find finest tf
        all_tfs: set[str] = set()
        for tfs in data.values():
            all_tfs.update(tfs.keys())

        if not all_tfs:
            return 0

        # Build master index from finest tf
        # (simple union for now; full alignment logic in TimeIndex)
        master_index = None
        for sym, tfs in data.items():
            for tf, df in tfs.items():
                if master_index is None:
                    master_index = df.index
                else:
                    master_index = master_index.union(df.index)

        if master_index is None or len(master_index) == 0:
            return 0

        master_index = master_index.sort_values()
        count = 0
        for t in master_index:
            payload: dict = {}
            for sym, tfs in data.items():
                payload[sym] = {}
                for tf, df in tfs.items():
                    # ffill align to master index
                    aligned = df.reindex(df.index.union([t])).sort_index().ffill()
                    if t in aligned.index:
                        payload[sym][tf] = aligned.loc[t]
            self._bus.publish(self._topic, {"ts": t, "bars": payload}, source=source)
            count += 1
        return count


# Module-level singleton
_bus: Optional[EventBus] = None


def get_bus() -> EventBus:
    """Return the global event bus singleton."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_bus() -> None:
    """Reset the global event bus (for testing)."""
    global _bus
    _bus = None
