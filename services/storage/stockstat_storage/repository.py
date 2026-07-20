from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Protocol

import pandas as pd
from stockstat_contracts import ArtifactRef, DatasetSnapshotManifest, InstrumentRef
from stockstat_contracts.time import format_utc

MARKET_COLUMNS = (
    "instrument_key",
    "asset_class",
    "symbol",
    "venue",
    "currency",
    "timeframe",
    "ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
    "ingest_batch_id",
    "normalization_version",
)


class StorageRepository(Protocol):
    query_count: int

    def initialize(self) -> None: ...
    def upsert_ohlcv(
        self,
        instrument: InstrumentRef,
        timeframe: str,
        source: str,
        ingest_batch_id: str,
        frame: pd.DataFrame,
        normalization_version: str = "1",
    ) -> int: ...
    def query_ohlcv(
        self,
        instruments: tuple[InstrumentRef, ...],
        timeframe: str,
        start: datetime,
        end: datetime,
        source: str | None = None,
    ) -> pd.DataFrame: ...
    def watermarks(
        self, instruments: tuple[InstrumentRef, ...], timeframe: str
    ) -> dict[str, str]: ...
    def save_artifact(self, reference: ArtifactRef, metadata: dict) -> None: ...
    def get_artifact(self, artifact_id: str) -> ArtifactRef | None: ...
    def get_artifact_metadata(self, artifact_id: str) -> dict | None: ...
    def artifact_digests(self) -> set[str]: ...
    def save_snapshot(self, manifest: DatasetSnapshotManifest, cache_key: str) -> None: ...
    def get_snapshot_by_cache_key(self, cache_key: str) -> DatasetSnapshotManifest | None: ...


class SQLiteStorageRepository:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.query_count = 0

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS ohlcv (
                    instrument_key TEXT NOT NULL, asset_class TEXT NOT NULL,
                    symbol TEXT NOT NULL, venue TEXT NOT NULL, currency TEXT,
                    timeframe TEXT NOT NULL, ts TEXT NOT NULL,
                    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,
                    close REAL NOT NULL, volume REAL NOT NULL, source TEXT NOT NULL,
                    ingest_batch_id TEXT NOT NULL, normalization_version TEXT NOT NULL,
                    PRIMARY KEY (instrument_key, timeframe, ts, source)
                );
                CREATE INDEX IF NOT EXISTS idx_ohlcv_range
                    ON ohlcv (instrument_key, timeframe, ts);
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL, metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    dataset_snapshot_id TEXT PRIMARY KEY, cache_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL
                );
            """)

    def upsert_ohlcv(
        self, instrument, timeframe, source, ingest_batch_id, frame, normalization_version="1"
    ):
        rows = _market_rows(
            instrument, timeframe, source, ingest_batch_id, frame, normalization_version
        )
        with self.connection() as connection:
            connection.executemany(
                """
                INSERT INTO ohlcv (
                    instrument_key, asset_class, symbol, venue, currency, timeframe, ts,
                    open, high, low, close, volume, source, ingest_batch_id,
                    normalization_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument_key, timeframe, ts, source) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume,
                    ingest_batch_id=excluded.ingest_batch_id,
                    normalization_version=excluded.normalization_version
            """,
                rows,
            )
        return len(rows)

    def query_ohlcv(self, instruments, timeframe, start, end, source=None):
        self.query_count += 1
        keys = [instrument.key for instrument in instruments]
        placeholders = ",".join("?" for _ in keys)
        query = f"""
            SELECT {", ".join(MARKET_COLUMNS)} FROM ohlcv
            WHERE instrument_key IN ({placeholders})
              AND timeframe = ? AND ts >= ? AND ts < ?
        """
        parameters = [*keys, timeframe, format_utc(start), format_utc(end)]
        if source:
            query += " AND source = ?"
            parameters.append(source)
        query += " ORDER BY instrument_key, ts"
        with self.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return _rows_to_frame(rows)

    def watermarks(self, instruments, timeframe):
        keys = [instrument.key for instrument in instruments]
        placeholders = ",".join("?" for _ in keys)
        with self.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT instrument_key,
                       COALESCE(MAX(ingest_batch_id || ':' || ts), '') watermark
                FROM ohlcv WHERE instrument_key IN ({placeholders}) AND timeframe = ?
                GROUP BY instrument_key
            """,
                [*keys, timeframe],
            ).fetchall()
        values = {row["instrument_key"]: row["watermark"] for row in rows}
        return {key: values.get(key, "") for key in keys}

    def save_artifact(self, reference, metadata):
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO artifacts (artifact_id, sha256, payload_json, metadata_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    sha256=excluded.sha256, payload_json=excluded.payload_json,
                    metadata_json=excluded.metadata_json
            """,
                (
                    reference.artifact_id,
                    reference.sha256,
                    reference.model_dump_json(),
                    json.dumps(metadata, sort_keys=True),
                ),
            )

    def get_artifact(self, artifact_id):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        return ArtifactRef.model_validate_json(row[0]) if row else None

    def get_artifact_metadata(self, artifact_id):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT metadata_json FROM artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def artifact_digests(self):
        with self.connection() as connection:
            rows = connection.execute("SELECT DISTINCT sha256 FROM artifacts").fetchall()
        return {row[0] for row in rows}

    def save_snapshot(self, manifest, cache_key):
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO snapshots (dataset_snapshot_id, cache_key, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    dataset_snapshot_id=excluded.dataset_snapshot_id,
                    payload_json=excluded.payload_json
            """,
                (manifest.dataset_snapshot_id, cache_key, manifest.model_dump_json()),
            )

    def get_snapshot_by_cache_key(self, cache_key):
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM snapshots WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        return DatasetSnapshotManifest.model_validate_json(row[0]) if row else None


class PostgresStorageRepository:
    schema = "stockstat_v31_storage"

    def __init__(
        self,
        url: str,
        *,
        min_pool_size: int = 1,
        max_pool_size: int = 10,
        connect_timeout_seconds: int = 10,
        statement_timeout_ms: int = 30_000,
    ):
        self.url = url
        self.query_count = 0
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(
            conninfo=url,
            min_size=min_pool_size,
            max_size=max_pool_size,
            timeout=connect_timeout_seconds,
            kwargs={"options": f"-c statement_timeout={statement_timeout_ms}"},
            open=True,
        )

    @contextmanager
    def connection(self):
        with self.pool.connection() as connection:
            yield connection

    def close(self):
        self.pool.close()

    def initialize(self):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.schema}.ohlcv (
                    instrument_key TEXT NOT NULL, asset_class TEXT NOT NULL,
                    symbol TEXT NOT NULL, venue TEXT NOT NULL, currency TEXT,
                    timeframe TEXT NOT NULL, ts TIMESTAMPTZ NOT NULL,
                    open DOUBLE PRECISION NOT NULL, high DOUBLE PRECISION NOT NULL,
                    low DOUBLE PRECISION NOT NULL, close DOUBLE PRECISION NOT NULL,
                    volume DOUBLE PRECISION NOT NULL, source TEXT NOT NULL,
                    ingest_batch_id TEXT NOT NULL, normalization_version TEXT NOT NULL,
                    PRIMARY KEY (instrument_key, timeframe, ts, source)
                )
            """)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.schema}.artifacts (
                    artifact_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                    payload_json JSONB NOT NULL, metadata_json JSONB NOT NULL
                )
            """)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.schema}.snapshots (
                    dataset_snapshot_id TEXT PRIMARY KEY, cache_key TEXT NOT NULL UNIQUE,
                    payload_json JSONB NOT NULL
                )
            """)

    def upsert_ohlcv(
        self, instrument, timeframe, source, ingest_batch_id, frame, normalization_version="1"
    ):
        rows = _market_rows(
            instrument, timeframe, source, ingest_batch_id, frame, normalization_version
        )
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.executemany(
                f"""
                INSERT INTO {self.schema}.ohlcv (
                    instrument_key, asset_class, symbol, venue, currency, timeframe, ts,
                    open, high, low, close, volume, source, ingest_batch_id,
                    normalization_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(instrument_key, timeframe, ts, source) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume,
                    ingest_batch_id=excluded.ingest_batch_id,
                    normalization_version=excluded.normalization_version
            """,
                rows,
            )
        return len(rows)

    def query_ohlcv(self, instruments, timeframe, start, end, source=None):
        self.query_count += 1
        keys = [instrument.key for instrument in instruments]
        query = f"""
            SELECT {", ".join(MARKET_COLUMNS)} FROM {self.schema}.ohlcv
            WHERE instrument_key = ANY(%s)
              AND timeframe = %s AND ts >= %s AND ts < %s
        """
        parameters = [keys, timeframe, start, end]
        if source:
            query += " AND source = %s"
            parameters.append(source)
        query += " ORDER BY instrument_key, ts"
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(query, parameters)
            rows = cursor.fetchall()
        return _rows_to_frame(rows)

    def watermarks(self, instruments, timeframe):
        keys = [instrument.key for instrument in instruments]
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT instrument_key,
                       COALESCE(MAX(ingest_batch_id || ':' || ts::text), '') watermark
                FROM {self.schema}.ohlcv
                WHERE instrument_key = ANY(%s) AND timeframe = %s
                GROUP BY instrument_key
            """,
                (keys, timeframe),
            )
            rows = cursor.fetchall()
        values = {row[0]: row[1] for row in rows}
        return {key: values.get(key, "") for key in keys}

    def save_artifact(self, reference, metadata):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {self.schema}.artifacts
                    (artifact_id, sha256, payload_json, metadata_json)
                VALUES (%s, %s, %s::jsonb, %s::jsonb)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    sha256=excluded.sha256, payload_json=excluded.payload_json,
                    metadata_json=excluded.metadata_json
            """,
                (
                    reference.artifact_id,
                    reference.sha256,
                    reference.model_dump_json(),
                    json.dumps(metadata, sort_keys=True),
                ),
            )

    def get_artifact(self, artifact_id):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT payload_json FROM {self.schema}.artifacts WHERE artifact_id = %s",
                (artifact_id,),
            )
            row = cursor.fetchone()
        return ArtifactRef.model_validate(row[0]) if row else None

    def get_artifact_metadata(self, artifact_id):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT metadata_json FROM {self.schema}.artifacts WHERE artifact_id = %s",
                (artifact_id,),
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def artifact_digests(self):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT DISTINCT sha256 FROM {self.schema}.artifacts")
            rows = cursor.fetchall()
        return {row[0] for row in rows}

    def save_snapshot(self, manifest, cache_key):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {self.schema}.snapshots
                    (dataset_snapshot_id, cache_key, payload_json)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT(cache_key) DO UPDATE SET
                    dataset_snapshot_id=excluded.dataset_snapshot_id,
                    payload_json=excluded.payload_json
            """,
                (manifest.dataset_snapshot_id, cache_key, manifest.model_dump_json()),
            )

    def get_snapshot_by_cache_key(self, cache_key):
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT payload_json FROM {self.schema}.snapshots WHERE cache_key = %s",
                (cache_key,),
            )
            row = cursor.fetchone()
        return DatasetSnapshotManifest.model_validate(row[0]) if row else None


def _market_rows(instrument, timeframe, source, ingest_batch_id, frame, normalization_version):
    normalized = frame.copy()
    normalized.index = pd.to_datetime(normalized.index, utc=True)
    normalized = normalized.sort_index()
    return [
        (
            instrument.key,
            instrument.asset_class,
            instrument.symbol,
            instrument.venue,
            instrument.currency,
            timeframe,
            format_utc(timestamp.to_pydatetime()),
            float(values.open),
            float(values.high),
            float(values.low),
            float(values.close),
            float(values.volume),
            source,
            ingest_batch_id,
            normalization_version,
        )
        for timestamp, values in normalized.iterrows()
    ]


def _rows_to_frame(rows):
    if not rows:
        return pd.DataFrame(columns=MARKET_COLUMNS)
    frame = pd.DataFrame([tuple(row) for row in rows], columns=MARKET_COLUMNS)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame
