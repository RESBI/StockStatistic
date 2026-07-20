from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Float,
    Integer,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class OHLCV(Base):
    __tablename__ = "ohlcv"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    ts = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    source = Column(String(50), nullable=False)
    timeframe = Column(String(10), nullable=False, default="1d")
    ingested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("symbol", "ts", "timeframe", "source", name="uq_ohlcv_key"),
        Index("ix_ohlcv_symbol_ts", "symbol", "ts"),
    )


class SymbolRegistry(Base):
    __tablename__ = "symbol_registry"

    unified_symbol = Column(String(50), primary_key=True)
    asset_type = Column(String(20), nullable=False)
    base_asset = Column(String(30), nullable=False)
    quote_asset = Column(String(30), nullable=True)
    description = Column(String(200), nullable=True)
    sources = Column(String(200), nullable=True)
