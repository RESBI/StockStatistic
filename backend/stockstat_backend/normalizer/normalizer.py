from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def normalize_ohlcv(
    df: pd.DataFrame,
    symbol: str,
    source: str,
    timeframe: str = "1d",
) -> list[dict]:
    if df.empty:
        return []

    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required OHLCV columns: {missing}")

    df = df[list(required)].dropna(subset=["open", "high", "low", "close"])

    rows = []
    for ts, row in df.iterrows():
        rows.append({
            "symbol": symbol,
            "ts": ts.to_pydatetime(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
            "source": source,
            "timeframe": timeframe,
        })
    return rows
