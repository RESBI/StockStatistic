"""OHLCV SQLAlchemy 模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, DateTime, Float, Integer, Index
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""
    pass


class OHLCV(Base):
    """OHLCV K 线数据模型。

    主键：(symbol, timeframe, timestamp) 复合主键，避免重复插入。
    """
    __tablename__ = "ohlcv"

    symbol = Column(String(64), primary_key=True)
    timeframe = Column(String(8), primary_key=True)
    timestamp = Column(DateTime, primary_key=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False, default=0.0)

    __table_args__ = (
        Index("ix_ohlcv_symbol_tf_ts", "symbol", "timeframe", "timestamp"),
        Index("ix_ohlcv_ts", "timestamp"),
    )

    def __repr__(self) -> str:
        return (
            f"OHLCV(symbol={self.symbol!r}, timeframe={self.timeframe!r}, "
            f"timestamp={self.timestamp!r}, close={self.close})"
        )


class SymbolMetadata(Base):
    """标的元数据。"""
    __tablename__ = "symbol_metadata"

    symbol = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=True)
    exchange = Column(String(32), nullable=True)
    asset_class = Column(String(32), nullable=True)  # crypto/stock/forex/commodity
    first_seen = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, nullable=True)
    metadata_json = Column(String, nullable=True)  # JSON 字符串

    def __repr__(self) -> str:
        return f"SymbolMetadata(symbol={self.symbol!r}, name={self.name!r})"


__all__ = ["Base", "OHLCV", "SymbolMetadata"]
