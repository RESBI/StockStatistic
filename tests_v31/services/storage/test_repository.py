from datetime import UTC, datetime, timedelta

import pandas as pd
from stockstat_contracts import InstrumentRef
from stockstat_storage.repository import SQLiteStorageRepository


def sample_frame(start: datetime, rows: int = 4):
    index = pd.date_range(start, periods=rows, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "open": range(100, 100 + rows),
            "high": range(101, 101 + rows),
            "low": range(99, 99 + rows),
            "close": range(100, 100 + rows),
            "volume": 1000.0,
        },
        index=index,
    )


def test_sqlite_upsert_and_half_open_query(tmp_path):
    repository = SQLiteStorageRepository(tmp_path / "storage.db")
    repository.initialize()
    instrument = InstrumentRef(asset_class="crypto", symbol="PAXG/USDT", venue="binance")
    start = datetime(2024, 1, 1, tzinfo=UTC)
    frame = sample_frame(start)
    assert repository.upsert_ohlcv(instrument, "1h", "synthetic", "batch-1", frame) == 4
    assert repository.upsert_ohlcv(instrument, "1h", "synthetic", "batch-1", frame) == 4
    result = repository.query_ohlcv(
        (instrument,), "1h", start, start + timedelta(hours=3), "synthetic"
    )
    assert len(result) == 3
    assert result.ts.max() < start + timedelta(hours=3)
