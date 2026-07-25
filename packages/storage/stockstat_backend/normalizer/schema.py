"""数据规范化 — 字段映射 / 时区对齐 / 去重。"""
from __future__ import annotations

import pandas as pd


SCHEMA_MAP = {
    "binance": {
        "timestamp": "timestamp",
        "open": "open", "high": "high",
        "low": "low", "close": "close", "volume": "volume",
    },
    "yfinance": {
        "timestamp": "timestamp",
        "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "volume",
    },
    "synthetic": {
        "timestamp": "timestamp",
        "open": "open", "high": "high",
        "low": "low", "close": "close", "volume": "volume",
    },
}


class Normalizer:
    """数据规范化 — 不同源的字段映射、时区对齐。"""

    def normalize(self, df: pd.DataFrame, source: str = "binance") -> pd.DataFrame:
        """规范化 DataFrame。"""
        if df is None or len(df) == 0:
            return df
        mapping = SCHEMA_MAP.get(source, {})
        if mapping:
            df = df.rename(columns=mapping)
        # 时区对齐：统一为 UTC
        if "timestamp" in df.columns:
            ts = df["timestamp"]
            if hasattr(ts, "dt") and ts.dt.tz is not None:
                df["timestamp"] = ts.dt.tz_convert("UTC")
            elif hasattr(ts, "dt") and ts.dt.tz is None:
                # 已是 naive，假设是 UTC
                pass
            # 去重
            df = df.drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
        # 类型规范化
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df


__all__ = ["Normalizer", "SCHEMA_MAP"]
