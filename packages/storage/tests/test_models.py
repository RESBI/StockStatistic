"""test_models.py — OHLCV 模型 / 复合主键 / 索引 (15 项)。"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import inspect

from stockstat_backend.models import Base, OHLCV, SymbolMetadata


class TestOHLCVModel:
    def test_table_name(self):
        assert OHLCV.__tablename__ == "ohlcv"

    def test_columns(self):
        cols = {c.name for c in inspect(OHLCV).columns}
        assert cols == {"symbol", "timeframe", "timestamp",
                        "open", "high", "low", "close", "volume"}

    def test_composite_primary_key(self):
        pk = [c.name for c in inspect(OHLCV).primary_key]
        assert pk == ["symbol", "timeframe", "timestamp"]

    def test_indexes(self):
        from sqlalchemy import inspect as sa_inspect
        # 通过 Table 检查索引（而非 Mapper）
        indexes = {idx.name for idx in OHLCV.__table__.indexes}
        assert "ix_ohlcv_symbol_tf_ts" in indexes
        assert "ix_ohlcv_ts" in indexes

    def test_create_ohlcv_instance(self):
        r = OHLCV(symbol="BTC/USDT", timeframe="1d",
                  timestamp=datetime(2024, 1, 1),
                  open=100, high=110, low=95, close=105, volume=1000)
        assert r.symbol == "BTC/USDT"
        assert r.close == 105

    def test_repr(self):
        r = OHLCV(symbol="BTC", timeframe="1d",
                  timestamp=datetime(2024, 1, 1),
                  open=1, high=2, low=0.5, close=1.5, volume=10)
        s = repr(r)
        assert "BTC" in s
        assert "1d" in s

    def test_volume_default(self):
        r = OHLCV(symbol="BTC", timeframe="1d",
                  timestamp=datetime(2024, 1, 1),
                  open=1, high=2, low=0.5, close=1.5)
        # volume 是 nullable=False, default=0.0 — 但 SQLAlchemy default 在 commit 时填充
        # 这里测试列定义
        col = inspect(OHLCV).columns["volume"]
        assert col.nullable is False


class TestSymbolMetadata:
    def test_table_name(self):
        assert SymbolMetadata.__tablename__ == "symbol_metadata"

    def test_primary_key(self):
        pk = [c.name for c in inspect(SymbolMetadata).primary_key]
        assert pk == ["symbol"]

    def test_columns(self):
        cols = {c.name for c in inspect(SymbolMetadata).columns}
        assert "name" in cols
        assert "exchange" in cols
        assert "asset_class" in cols
        assert "metadata_json" in cols

    def test_create(self):
        m = SymbolMetadata(symbol="BTC/USDT", name="Bitcoin",
                           exchange="binance", asset_class="crypto")
        assert m.symbol == "BTC/USDT"
        assert m.asset_class == "crypto"

    def test_repr(self):
        m = SymbolMetadata(symbol="ETH", name="Ethereum")
        assert "ETH" in repr(m)


class TestBase:
    def test_base_is_declarative(self):
        from sqlalchemy.orm import DeclarativeBase
        assert issubclass(Base, DeclarativeBase)

    def test_metadata_has_tables(self):
        # 在创建 engine 前，metadata 应注册了两个表
        table_names = set(Base.metadata.tables.keys())
        assert "ohlcv" in table_names
        assert "symbol_metadata" in table_names

    def test_base_separate_from_other_bases(self):
        # 确保不是全局 Base
        from sqlalchemy.orm import registry
        assert isinstance(Base.registry, registry)
