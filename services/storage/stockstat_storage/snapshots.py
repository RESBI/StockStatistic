from __future__ import annotations

import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc
from stockstat_contracts import (
    DatasetSelector,
    DatasetSnapshotManifest,
    canonical_digest,
    new_id,
)
from stockstat_contracts.time import utc_now

from .artifacts import ArtifactService
from .repository import StorageRepository


class SnapshotService:
    def __init__(self, repository: StorageRepository, artifacts: ArtifactService):
        self.repository = repository
        self.artifacts = artifacts

    def create(self, selector: DatasetSelector) -> DatasetSnapshotManifest:
        watermarks = self.repository.watermarks(selector.instruments, selector.timeframe)
        selector_digest = canonical_digest(selector)
        cache_key = canonical_digest(
            {
                "selector": selector,
                "watermarks": watermarks,
                "normalization_version": "1",
                "schema": "stockstat.market.ohlcv/1",
            }
        )
        cached = self.repository.get_snapshot_by_cache_key(cache_key)
        if cached and self.artifacts.blob_store.exists(cached.artifact.sha256):
            return cached
        source = selector.source_policy.source if selector.source_policy.mode == "exact" else None
        frame = self.repository.query_ohlcv(
            selector.instruments, selector.timeframe, selector.start, selector.end, source
        )
        if frame.empty:
            raise LookupError("DATA_NOT_FOUND")
        arrow_frame = frame.rename(columns={"instrument_key": "instrument"})
        columns = [
            "ts",
            "instrument",
            "timeframe",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "source",
            "ingest_batch_id",
        ]
        table = pa.Table.from_pandas(arrow_frame.loc[:, columns], preserve_index=False)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".arrow", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                with ipc.new_stream(temporary, table.schema) as writer:
                    for batch in table.to_batches(max_chunksize=65_536):
                        writer.write_batch(batch)
            artifact = self.artifacts.commit_file(
                temporary_path,
                kind="market_data_snapshot",
                media_type="application/vnd.apache.arrow.stream",
                codec="arrow-ipc-stream",
                schema_ref="stockstat.market.ohlcv/1",
                metadata={"selector_digest": selector_digest, "watermarks": watermarks},
            )
        finally:
            if temporary_path:
                temporary_path.unlink(missing_ok=True)
        manifest = DatasetSnapshotManifest(
            dataset_snapshot_id=new_id(),
            selector_digest=selector_digest,
            resolved_instruments=selector.instruments,
            timeframe=selector.timeframe,
            resolved_start=frame.ts.min().to_pydatetime(),
            resolved_end=frame.ts.max().to_pydatetime(),
            row_count=len(frame),
            schema_ref="stockstat.market.ohlcv/1",
            artifact=artifact,
            ingest_batch_ids=tuple(sorted(set(frame.ingest_batch_id))),
            created_at=utc_now(),
            sha256=artifact.sha256,
        )
        self.repository.save_snapshot(manifest, cache_key)
        return manifest
