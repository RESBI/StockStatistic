from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from stockstat_contracts.time import format_utc


def now_text() -> str:
    return format_utc(datetime.now(UTC))


class TaskStore(Protocol):
    lock: threading.RLock

    def initialize(self) -> None: ...
    def execute(self, statement: str, parameters=()) -> int: ...
    def fetchone(self, statement: str, parameters=()) -> dict | None: ...
    def fetchall(self, statement: str, parameters=()) -> list[dict]: ...
    def transaction(self): ...


class SQLiteTaskStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.lock = threading.RLock()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        with self.lock, self.connection() as connection:
            yield SQLiteTransaction(connection)

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    spec_json TEXT NOT NULL,
                    spec_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    priority INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    deadline_at TEXT,
                    result_json TEXT,
                    error_json TEXT
                );
                CREATE TABLE IF NOT EXISTS stages (
                    stage_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    name TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS work_units (
                    work_unit_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    stage_id TEXT NOT NULL REFERENCES stages(stage_id),
                    state TEXT NOT NULL,
                    capability_id TEXT NOT NULL,
                    capability_version TEXT NOT NULL,
                    executor_role TEXT NOT NULL,
                    work_json TEXT NOT NULL,
                    attempt_generation INTEGER NOT NULL DEFAULT 0,
                    current_attempt_id TEXT,
                    not_before TEXT,
                    result_json TEXT,
                    error_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_work_ready
                    ON work_units(state, capability_id, not_before);
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY,
                    work_unit_id TEXT NOT NULL REFERENCES work_units(work_unit_id),
                    generation INTEGER NOT NULL,
                    worker_id TEXT NOT NULL,
                    worker_session_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    lease_expires_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    completion_id TEXT UNIQUE,
                    failure_id TEXT UNIQUE,
                    result_json TEXT,
                    error_json TEXT
                );
                CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY,
                    current_session_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    resources_json TEXT NOT NULL,
                    last_heartbeat_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS job_events (
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (job_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    idempotency_key TEXT PRIMARY KEY,
                    request_digest TEXT NOT NULL,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ingest_schedules (
                    schedule_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    next_run_at TEXT,
                    last_run_at TEXT
                );
                """
            )

    def execute(self, statement: str, parameters=()) -> int:
        with self.transaction() as transaction:
            return transaction.execute(statement, parameters)

    def fetchone(self, statement: str, parameters=()) -> dict | None:
        with self.connection() as connection:
            row = connection.execute(statement, parameters).fetchone()
        return dict(row) if row else None

    def fetchall(self, statement: str, parameters=()) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [dict(row) for row in rows]


class SQLiteTransaction:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def execute(self, statement: str, parameters=()) -> int:
        return self.connection.execute(statement, parameters).rowcount

    def fetchone(self, statement: str, parameters=()) -> dict | None:
        row = self.connection.execute(statement, parameters).fetchone()
        return dict(row) if row else None

    def fetchall(self, statement: str, parameters=()) -> list[dict]:
        return [dict(row) for row in self.connection.execute(statement, parameters).fetchall()]


class PostgresTaskStore:
    schema = "stockstat_v31_dispatcher"

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
        self.lock = threading.RLock()
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(
            conninfo=url,
            min_size=min_pool_size,
            max_size=max_pool_size,
            timeout=connect_timeout_seconds,
            kwargs={
                "options": f"-c statement_timeout={statement_timeout_ms}",
                "row_factory": _dict_row,
            },
            open=True,
        )

    @contextmanager
    def connection(self):
        with self.pool.connection() as connection:
            yield connection

    def close(self):
        self.pool.close()

    @contextmanager
    def transaction(self):
        with self.connection() as connection:
            yield PostgresTransaction(connection, self.schema)

    def initialize(self) -> None:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.schema}.jobs (
                    job_id TEXT PRIMARY KEY, spec_json JSONB NOT NULL,
                    spec_digest TEXT NOT NULL, state TEXT NOT NULL,
                    revision INTEGER NOT NULL, priority INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL,
                    started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
                    deadline_at TIMESTAMPTZ, result_json JSONB, error_json JSONB
                );
                CREATE TABLE IF NOT EXISTS {self.schema}.stages (
                    stage_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES
                        {self.schema}.jobs(job_id), name TEXT NOT NULL,
                    position INTEGER NOT NULL, state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {self.schema}.work_units (
                    work_unit_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES
                        {self.schema}.jobs(job_id), stage_id TEXT NOT NULL REFERENCES
                        {self.schema}.stages(stage_id), state TEXT NOT NULL,
                    capability_id TEXT NOT NULL, capability_version TEXT NOT NULL,
                    executor_role TEXT NOT NULL, work_json JSONB NOT NULL,
                    attempt_generation INTEGER NOT NULL DEFAULT 0,
                    current_attempt_id TEXT, not_before TIMESTAMPTZ,
                    result_json JSONB, error_json JSONB
                );
                CREATE TABLE IF NOT EXISTS {self.schema}.attempts (
                    attempt_id TEXT PRIMARY KEY, work_unit_id TEXT NOT NULL REFERENCES
                        {self.schema}.work_units(work_unit_id), generation INTEGER NOT NULL,
                    worker_id TEXT NOT NULL, worker_session_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL, state TEXT NOT NULL,
                    lease_expires_at TIMESTAMPTZ NOT NULL,
                    started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
                    completion_id TEXT UNIQUE, failure_id TEXT UNIQUE,
                    result_json JSONB, error_json JSONB
                );
                CREATE TABLE IF NOT EXISTS {self.schema}.workers (
                    worker_id TEXT PRIMARY KEY, current_session_id TEXT NOT NULL,
                    state TEXT NOT NULL, capabilities_json JSONB NOT NULL,
                    resources_json JSONB NOT NULL,
                    last_heartbeat_at TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {self.schema}.job_events (
                    job_id TEXT NOT NULL REFERENCES {self.schema}.jobs(job_id),
                    sequence INTEGER NOT NULL, event_type TEXT NOT NULL,
                    occurred_at TIMESTAMPTZ NOT NULL, payload_json JSONB NOT NULL,
                    PRIMARY KEY (job_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS {self.schema}.idempotency_keys (
                    idempotency_key TEXT PRIMARY KEY, request_digest TEXT NOT NULL,
                    job_id TEXT NOT NULL REFERENCES {self.schema}.jobs(job_id),
                    created_at TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {self.schema}.ingest_schedules (
                    schedule_id TEXT PRIMARY KEY, payload_json JSONB NOT NULL,
                    enabled BOOLEAN NOT NULL, next_run_at TIMESTAMPTZ,
                    last_run_at TIMESTAMPTZ
                );
                """
            )
            cursor.execute(
                f"""CREATE INDEX IF NOT EXISTS idx_work_ready
                ON {self.schema}.work_units(state, capability_id, not_before)"""
            )

    def execute(self, statement: str, parameters=()) -> int:
        with self.transaction() as transaction:
            return transaction.execute(statement, parameters)

    def fetchone(self, statement: str, parameters=()) -> dict | None:
        with self.transaction() as transaction:
            return transaction.fetchone(statement, parameters)

    def fetchall(self, statement: str, parameters=()) -> list[dict]:
        with self.transaction() as transaction:
            return transaction.fetchall(statement, parameters)


class PostgresTransaction:
    def __init__(self, connection, schema: str):
        self.connection = connection
        self.schema = schema

    def _sql(self, statement: str) -> str:
        translated = statement.replace("?", "%s")
        for table in (
            "jobs",
            "stages",
            "work_units",
            "attempts",
            "workers",
            "job_events",
            "idempotency_keys",
            "ingest_schedules",
        ):
            translated = re.sub(rf"(?<![.\w]){table}(?!\w)", f"{self.schema}.{table}", translated)
        return translated

    def execute(self, statement: str, parameters=()) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(self._sql(statement), parameters)
            return cursor.rowcount

    def fetchone(self, statement: str, parameters=()) -> dict | None:
        with self.connection.cursor() as cursor:
            cursor.execute(self._sql(statement), parameters)
            return cursor.fetchone()

    def fetchall(self, statement: str, parameters=()) -> list[dict]:
        with self.connection.cursor() as cursor:
            cursor.execute(self._sql(statement), parameters)
            return list(cursor.fetchall())


def encode(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def decode(value):
    if value is None or isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _dict_row(cursor):
    from psycopg.rows import dict_row

    return dict_row(cursor)
