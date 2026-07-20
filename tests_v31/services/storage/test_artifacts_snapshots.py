from datetime import UTC, datetime, timedelta

from stockstat_contracts import DatasetSelector, InstrumentRef, SourcePolicy
from stockstat_storage.artifacts import ArtifactService, LocalBlobStore
from stockstat_storage.repository import SQLiteStorageRepository
from stockstat_storage.snapshots import SnapshotService


def sample_frame(start, rows=4):
    import pandas as pd

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


def services(tmp_path):
    repository = SQLiteStorageRepository(tmp_path / "storage.db")
    repository.initialize()
    artifacts = ArtifactService(
        repository, LocalBlobStore(tmp_path / "artifacts"), tmp_path / "uploads"
    )
    return repository, artifacts, SnapshotService(repository, artifacts)


def test_artifact_commit_and_integrity(tmp_path):
    repository, artifacts, _ = services(tmp_path)
    path = tmp_path / "payload.bin"
    path.write_bytes(b"stockstat-v31")
    reference = artifacts.commit_file(
        path,
        kind="work_result",
        media_type="application/octet-stream",
        codec="raw",
        schema_ref="test/1",
    )
    assert repository.get_artifact(reference.artifact_id) == reference
    assert artifacts.read(reference) == b"stockstat-v31"


def test_snapshot_queries_market_database_once_and_reuses_content(tmp_path):
    repository, artifacts, snapshots = services(tmp_path)
    instrument = InstrumentRef(asset_class="crypto", symbol="PAXG/USDT", venue="binance")
    start = datetime(2024, 1, 1, tzinfo=UTC)
    repository.upsert_ohlcv(instrument, "1h", "synthetic", "batch-1", sample_frame(start))
    selector = DatasetSelector(
        instruments=(instrument,),
        timeframe="1h",
        start=start,
        end=start + timedelta(hours=4),
        source_policy=SourcePolicy(mode="exact", source="synthetic"),
    )
    first = snapshots.create(selector)
    second = snapshots.create(selector)
    assert first.artifact.sha256 == second.artifact.sha256
    assert repository.query_count == 1
    assert artifacts.read(first.artifact)
