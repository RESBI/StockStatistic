"""ScheduledCollector — 定时数据采集。"""
from __future__ import annotations

import threading
import time
from typing import Optional


class ScheduledCollector:
    """定时数据采集器。"""

    def __init__(self, storage_backend, adapters: dict, interval: int = 3600):
        self._storage = storage_backend
        self._adapters = adapters
        self._interval = interval
        self._subscriptions: list = []
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

    def subscribe(self, symbol: str, timeframe: str = "1d",
                  source: str = "binance") -> None:
        """订阅定时采集。"""
        with self._lock:
            self._subscriptions.append({
                "symbol": symbol, "timeframe": timeframe, "source": source,
            })

    def unsubscribe(self, symbol: str, timeframe: str = "1d") -> None:
        with self._lock:
            self._subscriptions = [
                s for s in self._subscriptions
                if not (s["symbol"] == symbol and s["timeframe"] == timeframe)
            ]

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def run_once(self) -> dict:
        """立即执行一次采集，返回结果统计。"""
        results = {"success": 0, "failed": 0, "errors": []}
        with self._lock:
            subs = list(self._subscriptions)
        for sub in subs:
            try:
                adapter_cls = self._adapters.get(sub["source"])
                if adapter_cls is None:
                    raise ValueError(f"Unknown adapter: {sub['source']}")
                adapter = adapter_cls()
                df = adapter.fetch_ohlcv(sub["symbol"], sub["timeframe"])
                self._storage.ingest_ohlcv(sub["symbol"], sub["timeframe"], df)
                results["success"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "symbol": sub["symbol"], "error": str(e)
                })
        return results

    def _loop(self) -> None:
        while self._running:
            try:
                self.run_once()
            except Exception:
                pass
            time.sleep(self._interval)


__all__ = ["ScheduledCollector"]
