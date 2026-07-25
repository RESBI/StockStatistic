"""Storage backend protocol — abstracts persistence of time-series data."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

import pandas as pd


@dataclass
class FieldDef:
    """A single field in a data schema."""
    name: str
    dtype: str  # "float", "str", "datetime", "int"
    nullable: bool = True
    primary_key: bool = False


@dataclass
class DataSchema:
    """Schema describing a time-series table."""
    name: str
    fields: list[FieldDef] = field(default_factory=list)
    time_field: str = "ts"
    symbol_field: str = "symbol"
    unique_constraints: list[tuple[str, ...]] = field(default_factory=list)

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]


@runtime_checkable
class StorageBackend(Protocol):
    """Abstract storage backend.

    Implementations: MemoryStorage, SQLStorage (SQLAlchemy),
    TimescaleStorage, ParquetStorage.
    """
    name: str

    def query(
        self,
        table: str,
        filters: Optional[dict] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame: ...

    def write(self, table: str, records: list[dict]) -> int: ...

    def upsert(self, table: str, records: list[dict]) -> int: ...

    def delete(self, table: str, filters: Optional[dict] = None) -> int: ...

    def count(self, table: str, filters: Optional[dict] = None) -> int: ...

    def schema(self, table: str) -> Optional[DataSchema]: ...

    def health_check(self) -> bool: ...
