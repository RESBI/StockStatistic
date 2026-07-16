"""Intrabar simulator for fine-grained limit order fill simulation."""
from __future__ import annotations

from typing import Optional
import pandas as pd


class IntrabarSimulator:
    """Simulate limit/stop order fills using finer-grained bars.

    Usage in a strategy:
        sim = IntrabarSimulator(fine_data_1h)
        fill_price, fill_time = sim.check_fill(
            price_level=100.0, side="buy",
            start_ts=mon_date, end_ts=mon_date + pd.Timedelta(days=1)
        )
    """

    def __init__(self, fine_data: pd.DataFrame):
        if not isinstance(fine_data.index, pd.DatetimeIndex):
            fine_data = fine_data.copy()
            fine_data.index = pd.to_datetime(fine_data.index)
        self._data = fine_data.sort_index()

    def check_fill(self, price_level: float, side: str,
                   start_ts: pd.Timestamp,
                   end_ts: Optional[pd.Timestamp] = None
                   ) -> tuple[Optional[float], Optional[pd.Timestamp]]:
        """Check if a price level is touched between start_ts and end_ts.

        Returns (fill_price, fill_timestamp) or (None, None).
        """
        if end_ts is None:
            end_ts = start_ts + pd.Timedelta(days=1)

        bars = self._data.loc[(self._data.index >= start_ts) &
                              (self._data.index < end_ts)]

        for ts, bar in bars.iterrows():
            if bar["low"] <= price_level <= bar["high"]:
                return float(price_level), ts
        return None, None

    def check_fill_sequence(self, levels: list[tuple[float, str]],
                            start_ts: pd.Timestamp,
                            end_ts: Optional[pd.Timestamp] = None
                            ) -> list[tuple[float, str, pd.Timestamp]]:
        """Check multiple price levels, return all that fill in order of time.

        Each level is (price, side). Returns list of (price, side, timestamp).
        """
        if end_ts is None:
            end_ts = start_ts + pd.Timedelta(days=1)
        bars = self._data.loc[(self._data.index >= start_ts) &
                              (self._data.index < end_ts)]
        results = []
        for ts, bar in bars.iterrows():
            for price, side in levels:
                if bar["low"] <= price <= bar["high"]:
                    results.append((float(price), side, ts))
            if results:
                break
        return results

    def first_to_fill(self, levels: list[tuple[float, str]],
                      start_ts: pd.Timestamp,
                      end_ts: Optional[pd.Timestamp] = None
                      ) -> Optional[tuple[float, str, pd.Timestamp]]:
        """Return the first level to fill, or None."""
        results = self.check_fill_sequence(levels, start_ts, end_ts)
        return results[0] if results else None
