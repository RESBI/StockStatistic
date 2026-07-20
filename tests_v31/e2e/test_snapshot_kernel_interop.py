from datetime import UTC, datetime, timedelta

import pandas as pd
import pyarrow.ipc as ipc
from stockstat_contracts import DatasetSelector, InstrumentRef, SourcePolicy
from stockstat_kernel import MarketDataset
from stockstat_storage.artifacts import ArtifactService, LocalBlobStore
from stockstat_storage.repository import SQLiteStorageRepository
from stockstat_storage.snapshots import SnapshotService


def test_snapshot_loads_directly_into_kernel(tmp_path):
    repository = SQLiteStorageRepository(tmp_path / "storage.db")
    repository.initialize()
    artifacts = ArtifactService(
        repository, LocalBlobStore(tmp_path / "artifacts"), tmp_path / "uploads"
    )
    service = SnapshotService(repository, artifacts)
    instrument = InstrumentRef(asset_class="crypto", symbol="PAXG/USDT", venue="binance")
    start = datetime(2024, 1, 1, tzinfo=UTC)
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
    repository.upsert_ohlcv(instrument, "1h", "synthetic", "batch-1", frame)
    manifest = service.create(
        DatasetSelector(
            instruments=(instrument,),
            timeframe="1h",
            start=start,
            end=start + timedelta(hours=4),
            source_policy=SourcePolicy(mode="exact", source="synthetic"),
        )
    )
    with artifacts.blob_store.open(manifest.artifact.sha256) as stream:
        table = ipc.open_stream(stream).read_all()
    market = MarketDataset.from_arrow(table)
    assert market.universe.instruments == [instrument.key]
