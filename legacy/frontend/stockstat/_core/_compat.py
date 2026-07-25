"""Compatibility bridge between v2.0 core layer and v1.7 backend.

The v2.0 :class:`SQLStorage` delegates to these functions, which wrap
the existing v1.7 SQLAlchemy ORM. This keeps the storage protocol
clean while reusing the battle-tested ORM code.
"""
from __future__ import annotations

from typing import Any, Optional


def get_sqlalchemy_engine(database_url: str = ""):
    """Return ``(engine, session_factory, Base)`` from v1.7 backend.

    If ``database_url`` is empty, the v1.7 ``settings.database_url``
    is used (which reads the ``DATABASE_URL`` env var).
    """
    try:
        from stockstat_backend.storage.database import get_engine, get_session_factory
        from stockstat_backend.models.ohlcv import Base
    except ImportError:
        # Backend not installed (frontend-only environment)
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker, DeclarativeBase

        class Base(DeclarativeBase):
            pass

        url = database_url or "sqlite:///stockstat.db"
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        engine = create_engine(url, connect_args=connect_args, future=True)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        return engine, session_factory, Base

    if database_url:
        # Override the v1.7 settings
        from stockstat_backend.config import settings
        settings.database_url = database_url

    engine = get_engine()
    session_factory = get_session_factory()
    return engine, session_factory, Base


def query_ohlcv_table(engine, table, filters, start, end, limit):
    """Query OHLCV data via v1.7 repository."""
    from stockstat_backend.storage.repository import ohlcv_repo

    symbol = (filters or {}).get("symbol")
    source = (filters or {}).get("source")
    timeframe = (filters or {}).get("timeframe", "1d")

    return ohlcv_repo.query(
        symbol=symbol, source=source, start=start, end=end,
        timeframe=timeframe, limit=limit,
    )


def write_table(engine, table, records):
    """Write records to a table via v1.7 repository."""
    from stockstat_backend.storage.repository import ohlcv_repo
    return ohlcv_repo.upsert_many(records)


def upsert_table(engine, table, records):
    """Upsert records via v1.7 repository."""
    from stockstat_backend.storage.repository import ohlcv_repo
    return ohlcv_repo.upsert_many(records)


def delete_table(engine, table, filters):
    """Delete from a table via v1.7 repository."""
    from stockstat_backend.storage.repository import ohlcv_repo
    ohlcv_repo.delete_all()  # v1.7 only supports delete_all
    return 0


def count_table(engine, table, filters):
    """Count rows in a table via v1.7 repository."""
    from stockstat_backend.storage.repository import ohlcv_repo
    symbol = (filters or {}).get("symbol") if filters else None
    return ohlcv_repo.count(symbol)
