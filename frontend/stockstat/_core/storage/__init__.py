"""Storage backend implementations."""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from ..contracts.storage import DataSchema, FieldDef, StorageBackend


class MemoryStorage:
    """In-memory storage for testing and small datasets.

    Stores data as a dict of DataFrames, one per table name.
    Satisfies the :class:`StorageBackend` protocol.
    """
    name = "memory"

    def __init__(self) -> None:
        self._tables: dict[str, pd.DataFrame] = {}
        self._schemas: dict[str, DataSchema] = {}

    def register_schema(self, table: str, schema: DataSchema) -> None:
        self._schemas[table] = schema
        if table not in self._tables:
            self._tables[table] = pd.DataFrame()

    def query(
        self,
        table: str,
        filters: Optional[dict] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        df = self._tables.get(table)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.copy()
        if start and "ts" in df.columns:
            df = df[df["ts"] >= pd.Timestamp(start, tz="UTC")]
        if end and "ts" in df.columns:
            df = df[df["ts"] <= pd.Timestamp(end, tz="UTC")]
        if filters:
            for key, val in filters.items():
                if key in df.columns:
                    df = df[df[key] == val]
        if limit:
            df = df.tail(limit)
        return df

    def write(self, table: str, records: list[dict]) -> int:
        if not records:
            return 0
        new_df = pd.DataFrame(records)
        if table in self._tables and not self._tables[table].empty:
            self._tables[table] = pd.concat(
                [self._tables[table], new_df], ignore_index=True
            )
        else:
            self._tables[table] = new_df
        return len(records)

    def upsert(self, table: str, records: list[dict]) -> int:
        if not records:
            return 0
        existing = self._tables.get(table, pd.DataFrame())
        schema = self._schemas.get(table)
        unique_fields: tuple[str, ...] = ()
        if schema and schema.unique_constraints:
            unique_fields = schema.unique_constraints[0]

        if not existing.empty and unique_fields:
            for rec in records:
                mask = pd.Series([True] * len(existing))
                for uf in unique_fields:
                    if uf in existing.columns and uf in rec:
                        mask &= existing[uf] == rec[uf]
                if mask.any():
                    idx = mask.idxmax()
                    for k, v in rec.items():
                        existing.at[idx, k] = v
                else:
                    existing = pd.concat(
                        [existing, pd.DataFrame([rec])], ignore_index=True
                    )
            self._tables[table] = existing
        else:
            self.write(table, records)
        return len(records)

    def delete(self, table: str, filters: Optional[dict] = None) -> int:
        df = self._tables.get(table)
        if df is None or df.empty:
            return 0
        if filters is None:
            count = len(df)
            self._tables[table] = pd.DataFrame()
            return count
        mask = pd.Series([True] * len(df))
        for key, val in filters.items():
            if key in df.columns:
                mask &= df[key] == val
        count = mask.sum()
        self._tables[table] = df[~mask].copy()
        return int(count)

    def count(self, table: str, filters: Optional[dict] = None) -> int:
        df = self._tables.get(table)
        if df is None:
            return 0
        if filters:
            mask = pd.Series([True] * len(df))
            for key, val in filters.items():
                if key in df.columns:
                    mask &= df[key] == val
            return int(mask.sum())
        return len(df)

    def schema(self, table: str) -> Optional[DataSchema]:
        return self._schemas.get(table)

    def health_check(self) -> bool:
        return True

    def clear(self) -> None:
        """Clear all tables (for testing)."""
        self._tables.clear()


class SQLStorage:
    """SQLAlchemy-based storage.

    Wraps the existing v1.7 SQLAlchemy ORM path behind the
    :class:`StorageBackend` protocol. This is the default storage
    backend, using SQLite for local dev and PostgreSQL/TimescaleDB
    for production.
    """
    name = "sql"

    def __init__(self, database_url: str = "") -> None:
        from .._compat import get_sqlalchemy_engine

        self._database_url = database_url
        self._engine, self._session_factory, self._Base = get_sqlalchemy_engine(
            database_url
        )

    def query(
        self,
        table: str,
        filters: Optional[dict] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        # Delegate to v1.7 repository logic
        from .._compat import query_ohlcv_table

        return query_ohlcv_table(
            self._engine, table, filters, start, end, limit
        )

    def write(self, table: str, records: list[dict]) -> int:
        from .._compat import write_table

        return write_table(self._engine, table, records)

    def upsert(self, table: str, records: list[dict]) -> int:
        from .._compat import upsert_table

        return upsert_table(self._engine, table, records)

    def delete(self, table: str, filters: Optional[dict] = None) -> int:
        from .._compat import delete_table

        return delete_table(self._engine, table, filters)

    def count(self, table: str, filters: Optional[dict] = None) -> int:
        from .._compat import count_table

        return count_table(self._engine, table, filters)

    def schema(self, table: str) -> Optional[DataSchema]:
        return None  # v1.7 ORM-driven, schema not separately tracked

    def health_check(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False
