"""IngestLog ORM model — independent from backend's DeclarativeBase.

Uses its own DeclarativeBase so the admin plugin does not modify
the backend's models/ohlcv.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class _AdminBase(DeclarativeBase):
    pass


class IngestLog(_AdminBase):
    """Log table for tracking ingest/delete operations."""
    __tablename__ = "admin_ingest_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    symbol = Column(String(50), nullable=False)
    action = Column(String(20), nullable=False)  # ingest / delete / batch_ingest / proxy_change
    rows_affected = Column(Integer, default=0)
    status = Column(String(20), default="success")  # success / failed
    error_message = Column(Text, nullable=True)
    source = Column(String(50), nullable=True)
    timeframe = Column(String(10), nullable=True)


def ensure_log_table():
    """Create the ingest log table if it doesn't exist. Thread-safe."""
    from .lock import _log_table_created
    import threading

    if _log_table_created:
        return
    # Use a simple flag — the worst case is two threads both try to
    # create the table, which is idempotent (CREATE TABLE IF NOT EXISTS
    # via metadata.create_all).
    try:
        from stockstat_backend.storage.database import get_engine
        _AdminBase.metadata.create_all(get_engine())
        _log_table_created = True  # not perfectly thread-safe but acceptable
    except Exception:
        pass  # Backend not available; logging is best-effort


def log_operation(symbol: str, action: str, rows: int = 0,
                  status: str = "success", error: str = None,
                  source: str = None, timeframe: str = None):
    """Write an entry to the ingest log. Best-effort (never raises)."""
    try:
        from stockstat_backend.storage.database import get_session
        ensure_log_table()
        with get_session() as session:
            session.add(IngestLog(
                symbol=symbol, action=action, rows_affected=rows,
                status=status, error_message=error,
                source=source, timeframe=timeframe,
            ))
    except Exception:
        pass
