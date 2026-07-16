from __future__ import annotations

from typing import Optional

import pandas as pd

from .fill_model import LookaheadError


class Universe:
    """Set of instruments and their per-timeframe DataFrames."""

    def __init__(self, data: dict[str, dict[str, pd.DataFrame]]):
        # data: {symbol: {timeframe: df}}
        self._data: dict[str, dict[str, pd.DataFrame]] = {}
        for sym, tfs in data.items():
            self._data[sym] = {}
            for tf, df in tfs.items():
                if not isinstance(df.index, pd.DatetimeIndex):
                    df = df.copy()
                    df.index = pd.to_datetime(df.index, utc=True)
                self._data[sym][tf] = df.sort_index()

    @property
    def symbols(self) -> list[str]:
        return list(self._data.keys())

    def timeframes(self, symbol: str) -> list[str]:
        return list(self._data[symbol].keys())

    def raw(self, symbol: str, timeframe: str) -> pd.DataFrame:
        return self._data[symbol][timeframe]


class DataFeed:
    """Aligns multi-symbol multi-timeframe data to a master timeline.

    The finest timeframe drives the cursor; higher timeframes are forward-filled.
    Provides lookahead-safe slicing via `get_slice(symbol, tf, t, lookback)`.
    """

    def __init__(self, universe: Universe, primary_tf: Optional[str] = None):
        self.universe = universe
        all_tfs = {tf for sym in universe.symbols for tf in universe.timeframes(sym)}
        if not all_tfs:
            raise ValueError("Universe is empty")
        self.primary_tf = primary_tf or self._pick_finest(all_tfs)
        self._aligned: dict[str, dict[str, pd.DataFrame]] = {}
        self._master_index = self._build_master_index()
        for sym in universe.symbols:
            self._aligned[sym] = {}
            for tf in universe.timeframes(sym):
                df = universe.raw(sym, tf)
                self._aligned[sym][tf] = df.reindex(self._master_index, method="ffill")

    @staticmethod
    def _pick_finest(tfs: set[str]) -> str:
        order = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]
        for tf in order:
            if tf in tfs:
                return tf
        return sorted(tfs)[0]

    def _build_master_index(self) -> pd.DatetimeIndex:
        idx = None
        for sym in self.universe.symbols:
            tf = self.primary_tf if self.primary_tf in self.universe.timeframes(sym) else self.universe.timeframes(sym)[0]
            df = self.universe.raw(sym, tf)
            idx = df.index if idx is None else idx.union(df.index)
        return idx.sort_values().unique()

    @property
    def master_index(self) -> pd.DatetimeIndex:
        return self._master_index

    def bar_at(self, symbol: str, tf: str, t: pd.Timestamp) -> Optional[pd.Series]:
        df = self._aligned.get(symbol, {}).get(tf)
        if df is None:
            return None
        if t not in df.index:
            return None
        return df.loc[t]

    def get_slice(self, symbol: str, tf: str, t: pd.Timestamp,
                  lookback: Optional[int] = None) -> pd.DataFrame:
        df = self._aligned.get(symbol, {}).get(tf)
        if df is None:
            raise KeyError(f"No data for {symbol}@{tf}")
        sub = df.loc[:t]
        if len(sub) == 0:
            return df.iloc[0:0]
        if lookback is not None:
            sub = sub.iloc[-lookback:]
        return sub

    def close_series(self, symbol: str, tf: str) -> pd.Series:
        return self._aligned[symbol][tf]["close"]
