from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import numpy as np
import pandas as pd
from stockstat_contracts import InstrumentRef, new_id

from .repository import StorageRepository


class DataSource(Protocol):
    source_id: str

    def fetch_ohlcv(
        self, instrument: InstrumentRef, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame: ...


class SyntheticSource:
    source_id = "synthetic"

    def __init__(self, seed: int = 0):
        self.seed = seed

    def fetch_ohlcv(self, instrument, timeframe, start, end):
        frequency = {"1h": "h", "1d": "D"}.get(timeframe, timeframe)
        start_at = pd.Timestamp(start)
        end_at = pd.Timestamp(end)
        start_at = (
            start_at.tz_localize("UTC") if start_at.tz is None else start_at.tz_convert("UTC")
        )
        end_at = end_at.tz_localize("UTC") if end_at.tz is None else end_at.tz_convert("UTC")
        index = pd.date_range(start_at, end_at, inclusive="left", freq=frequency)
        rng = np.random.default_rng(self.seed + sum(instrument.key.encode("utf-8")))
        returns = rng.normal(0.0002, 0.01, len(index))
        close = 100.0 * np.exp(np.cumsum(returns))
        spread = rng.uniform(0.001, 0.01, len(index))
        open_ = np.r_[close[0], close[:-1]] if len(close) else close
        return pd.DataFrame(
            {
                "open": open_,
                "high": np.maximum(open_, close) * (1 + spread),
                "low": np.minimum(open_, close) * (1 - spread),
                "close": close,
                "volume": rng.uniform(100, 10_000, len(index)),
            },
            index=index,
        )


@dataclass(frozen=True)
class IngestResult:
    ingest_batch_id: str
    row_count: int
    rejected_count: int
    start: datetime
    end: datetime


class IngestionService:
    def __init__(self, repository: StorageRepository, sources: dict[str, DataSource]):
        self.repository = repository
        self.sources = sources

    def ingest(self, instrument, source, timeframe, start, end):
        frame = self.sources[source].fetch_ohlcv(instrument, timeframe, start, end)
        batch_id = new_id()
        count = self.repository.upsert_ohlcv(
            instrument, timeframe, source, batch_id, frame, normalization_version="1"
        )
        return IngestResult(batch_id, count, 0, start, end)
