"""Frontend-local synthetic data adapter (no backend dependency).

A lightweight copy of stockstat_backend.adapters.synthetic that generates
reproducible OHLCV data using geometric Brownian motion. Used when the
backend package is not installed.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

_BASE_PRICES = {
    "AAPL": 150.0, "^GSPC": 4500.0,
    "BTC/USDT": 40000.0, "ETH/USDT": 2200.0, "PAXG/USDT": 1800.0,
}
_VOLATILITY = {
    "AAPL": 0.015, "^GSPC": 0.008,
    "BTC/USDT": 0.035, "ETH/USDT": 0.040, "PAXG/USDT": 0.010,
}
_RNG_SEED = 42


class LocalSyntheticAdapter:
    name = "synthetic"
    source_type = "mixed"

    def fetch_ohlcv(self, symbol: str, start: Optional[str] = None,
                    end: Optional[str] = None, timeframe: str = "1d") -> pd.DataFrame:
        base_price = _BASE_PRICES.get(symbol, 100.0)
        vol = _VOLATILITY.get(symbol, 0.02)

        if start:
            start_dt = pd.Timestamp(start, tz="UTC")
        else:
            start_dt = pd.Timestamp("2023-01-01", tz="UTC")
        if end:
            end_dt = pd.Timestamp(end, tz="UTC")
        else:
            end_dt = pd.Timestamp.now(tz="UTC")

        freq_map = {"1d": "D", "1h": "1h", "1w": "W", "1m": "1min",
                    "5m": "5min", "15m": "15min", "30m": "30min",
                    "4h": "4h", "1mo": "MS"}
        freq = freq_map.get(timeframe, "D")
        dates = pd.date_range(start=start_dt, end=end_dt, freq=freq)
        if "/" not in symbol:
            dates = dates[dates.weekday < 5]

        if len(dates) == 0:
            return pd.DataFrame()

        seed = _RNG_SEED + hash(symbol) % 10000
        rng = np.random.RandomState(seed)
        n = len(dates)
        daily_returns = rng.normal(0.0003, vol, n)
        close_prices = base_price * np.exp(np.cumsum(daily_returns))
        intraday_vol = vol * 0.6
        open_prices = close_prices * (1 + rng.normal(0, intraday_vol * 0.3, n))
        high_prices = np.maximum(open_prices, close_prices) * (1 + np.abs(rng.normal(0, intraday_vol, n)))
        low_prices = np.minimum(open_prices, close_prices) * (1 - np.abs(rng.normal(0, intraday_vol, n)))
        volumes = rng.uniform(1e6, 5e7, n)

        df = pd.DataFrame({
            "open": open_prices, "high": high_prices,
            "low": low_prices, "close": close_prices, "volume": volumes,
        }, index=dates)
        df.index.name = "ts"
        return df

    def supports(self, symbol: str) -> bool:
        return True

    def health_check(self) -> bool:
        return True

    def probe_range(self, symbol: str, timeframe: str = "1d") -> tuple[str | None, str | None]:
        from datetime import datetime, timezone
        return "2020-01-01T00:00:00+00:00", datetime.now(timezone.utc).isoformat()
