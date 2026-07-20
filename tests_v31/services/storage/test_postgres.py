import os
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from stockstat_contracts import InstrumentRef
from stockstat_storage.repository import PostgresStorageRepository


@pytest.mark.postgres
def test_postgres_repository_contract():
    url = os.environ.get("STOCKSTAT_V31_POSTGRES_URL")
    if not url:
        pytest.skip("STOCKSTAT_V31_POSTGRES_URL is not set")
    repository = PostgresStorageRepository(url)
    repository.initialize()
    instrument = InstrumentRef(asset_class="test", symbol="PAXG-V31-TEST", venue="stockstat-test")
    start = datetime(2031, 1, 1, tzinfo=UTC)
    index = pd.date_range(start, periods=4, freq="h", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": range(100, 104),
            "high": range(101, 105),
            "low": range(99, 103),
            "close": range(100, 104),
            "volume": 1000.0,
        },
        index=index,
    )
    repository.upsert_ohlcv(instrument, "1h", "synthetic", "pg-batch-1", frame)
    result = repository.query_ohlcv(
        (instrument,), "1h", start, start + timedelta(hours=4), "synthetic"
    )
    assert len(result) == 4
