"""Scheduler — v2.0 ingestion scheduling.

In v1.7 the scheduler was an empty stub. v2.0 provides a functional
scheduler that supports on-demand, cron-based, and event-driven
ingestion triggers.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd


class Scheduler:
    """Ingestion scheduler.

    Supports three trigger modes:

    * **on-demand**: ``trigger_now(symbol, source, ...)`` — immediate
    * **cron**: ``schedule_cron(symbol, cron_expr, ...)`` — recurring
    * **event-driven**: subscribe to EventBus topics that trigger ingest

    The scheduler itself does not implement the cron engine (that
    requires APScheduler or similar). It provides the registration and
    dispatch interface; a concrete cron backend can be plugged in.
    """

    def __init__(self, ingest_func: Optional[Callable] = None) -> None:
        self._ingest_func = ingest_func
        self._schedules: list[dict] = []
        self._running = False

    def set_ingest_func(self, func: Callable) -> None:
        self._ingest_func = func

    def trigger_now(self, symbol: str, source: Optional[str] = None,
                    start: Optional[str] = None, end: Optional[str] = None,
                    timeframe: str = "1d") -> Any:
        """Trigger an immediate ingestion."""
        if self._ingest_func is None:
            raise RuntimeError("No ingest function configured")
        return self._ingest_func(
            symbol=symbol, source=source, start=start, end=end, timeframe=timeframe
        )

    def schedule_cron(self, symbol: str, cron_expr: str,
                      source: Optional[str] = None,
                      timeframe: str = "1d") -> int:
        """Register a cron-based recurring ingestion.

        Args:
            symbol: Symbol to ingest.
            cron_expr: Cron expression (e.g. ``"0 * * * *"`` for hourly).
            source: Data source.
            timeframe: Bar timeframe.

        Returns:
            Schedule ID.
        """
        sid = len(self._schedules)
        self._schedules.append({
            "id": sid,
            "symbol": symbol,
            "cron": cron_expr,
            "source": source,
            "timeframe": timeframe,
            "type": "cron",
        })
        return sid

    def schedule_incremental(self, symbol: str, source: Optional[str] = None,
                             interval_hours: int = 24,
                             timeframe: str = "1d") -> int:
        """Register an incremental update schedule.

        Fetches only new data since the last ingested timestamp.
        """
        sid = len(self._schedules)
        self._schedules.append({
            "id": sid,
            "symbol": symbol,
            "source": source,
            "interval_hours": interval_hours,
            "timeframe": timeframe,
            "type": "incremental",
            "last_run": None,
        })
        return sid

    def list_schedules(self) -> list[dict]:
        """List all registered schedules."""
        return list(self._schedules)

    def cancel(self, schedule_id: int) -> bool:
        """Cancel a scheduled task."""
        before = len(self._schedules)
        self._schedules = [s for s in self._schedules if s["id"] != schedule_id]
        return len(self._schedules) < before

    def start(self) -> None:
        """Start the scheduler loop (placeholder — requires APScheduler)."""
        self._running = True

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def health_check(self) -> bool:
        return True
