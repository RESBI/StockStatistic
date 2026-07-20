from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pyarrow as pa

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(OHLCV_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"OHLCV frame is missing columns: {sorted(missing)}")
    normalized = frame.loc[:, OHLCV_COLUMNS].copy()
    index = pd.to_datetime(normalized.index, utc=True)
    if index.has_duplicates:
        raise ValueError("OHLCV index must be unique")
    normalized.index = index
    normalized = normalized.sort_index()
    for column in OHLCV_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="raise").astype("float64")
    values = normalized.loc[:, ("open", "high", "low", "close")].to_numpy()
    if not np.isfinite(values).all():
        raise ValueError("OHLC prices must be finite")
    if (values < 0).any() or (normalized["volume"] < 0).any():
        raise ValueError("OHLCV values must be non-negative")
    if (normalized["high"] < normalized[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high is below another OHLC value")
    if (normalized["low"] > normalized[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low is above another OHLC value")
    normalized.index.name = "ts"
    return normalized


class Universe:
    def __init__(self, data: dict[str, dict[str, pd.DataFrame]]):
        if not data:
            raise ValueError("universe is empty")
        self._data = {
            instrument: {timeframe: normalize_frame(frame) for timeframe, frame in frames.items()}
            for instrument, frames in data.items()
        }
        if any(not frames for frames in self._data.values()):
            raise ValueError("every instrument requires at least one timeframe")

    @property
    def instruments(self) -> list[str]:
        return list(self._data)

    @property
    def symbols(self) -> list[str]:
        return self.instruments

    def timeframes(self, instrument: str) -> list[str]:
        return list(self._data[instrument])

    def frame(self, instrument: str, timeframe: str) -> pd.DataFrame:
        return self._data[instrument][timeframe]

    raw = frame


@dataclass(frozen=True)
class MarketDataset:
    universe: Universe
    snapshot_ids: tuple[str, ...] = ()
    lineage: dict[str, object] | None = None

    @classmethod
    def from_arrow(cls, table: pa.Table) -> MarketDataset:
        required = {"ts", "instrument", "timeframe", *OHLCV_COLUMNS}
        missing = required - set(table.column_names)
        if missing:
            raise ValueError(f"market table is missing columns: {sorted(missing)}")
        frame = table.to_pandas()
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        data: dict[str, dict[str, pd.DataFrame]] = {}
        for (instrument, timeframe), group in frame.groupby(
            ["instrument", "timeframe"], sort=False
        ):
            data.setdefault(str(instrument), {})[str(timeframe)] = group.set_index("ts").loc[
                :, OHLCV_COLUMNS
            ]
        return cls(Universe(data))

    @classmethod
    def from_batches(cls, batches: Iterator[pa.RecordBatch]) -> MarketDataset:
        return cls.from_arrow(pa.Table.from_batches(list(batches)))

    def to_arrow(self) -> pa.Table:
        frames = []
        for instrument in self.universe.instruments:
            for timeframe in self.universe.timeframes(instrument):
                frame = self.universe.frame(instrument, timeframe).reset_index()
                frame.insert(1, "instrument", instrument)
                frame.insert(2, "timeframe", timeframe)
                frames.append(frame)
        return pa.Table.from_pandas(pd.concat(frames, ignore_index=True), preserve_index=False)
