"""test_api.py — REST API 测试（ohlcv / symbols / health / ingest）(50 项)。"""
from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from stockstat_backend import (
    StorageApp, OrmSession, StorageBackendImpl, create_engine_from_url,
)
from stockstat_foundation import Config
from stockstat_foundation.codec import ArrowCodec


@pytest.fixture
def client(tmp_path, monkeypatch):
    """创建 TestClient。"""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("STOCKSTAT_DATABASE_URL", f"sqlite:///{db_path}")
    config = Config.from_env()
    app = StorageApp.create(config)
    return TestClient(app)


@pytest.fixture
def backend(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine_from_url(f"sqlite:///{db_path}")
    orm = OrmSession(engine)
    orm.create_all()
    return StorageBackendImpl(orm)


def _make_df(n=10, start="2024-01-01"):
    ts = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({
        "timestamp": ts,
        "open": range(n), "high": range(1, n + 1),
        "low": range(n), "close": range(2, n + 2),
        "volume": range(100, 100 + n),
    })


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "storage" in data

    def test_health_has_storage_stats(self, client):
        r = client.get("/health")
        data = r.json()
        assert "total_rows" in data["storage"]


class TestOhlcvGet:
    def test_get_returns_404_when_empty(self, client):
        r = client.get("/api/v1/ohlcv", params={"symbol": "BTC", "timeframe": "1d"})
        assert r.status_code == 404

    def test_get_after_ingest(self, client):
        # 先写入
        df = _make_df(10)
        arrow_bytes = ArrowCodec().encode(df)
        client.post("/api/v1/ohlcv", content=arrow_bytes,
                    headers={"Content-Type": "application/vnd.apache.arrow.file",
                             "X-Symbol": "BTC", "X-Timeframe": "1d"})
        r = client.get("/api/v1/ohlcv", params={"symbol": "BTC", "timeframe": "1d"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/vnd.apache.arrow.file"
        df2 = ArrowCodec().decode(r.content)
        assert len(df2) == 10

    def test_get_json_format(self, client):
        df = _make_df(5)
        arrow_bytes = ArrowCodec().encode(df)
        client.post("/api/v1/ohlcv", content=arrow_bytes,
                    headers={"Content-Type": "application/vnd.apache.arrow.file",
                             "X-Symbol": "BTC", "X-Timeframe": "1d"})
        r = client.get("/api/v1/ohlcv",
                       params={"symbol": "BTC", "timeframe": "1d", "format": "json"})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 5

    def test_get_multi_symbol(self, client):
        for sym in ["BTC", "ETH"]:
            df = _make_df(3)
            arrow_bytes = ArrowCodec().encode(df)
            client.post("/api/v1/ohlcv", content=arrow_bytes,
                        headers={"Content-Type": "application/vnd.apache.arrow.file",
                                 "X-Symbol": sym, "X-Timeframe": "1d"})
        r = client.get("/api/v1/ohlcv", params={"symbol": "BTC,ETH", "timeframe": "1d"})
        assert r.status_code == 200
        df = ArrowCodec().decode(r.content)
        assert len(df) == 6  # 3 + 3
        assert set(df["symbol"]) == {"BTC", "ETH"}

    def test_get_with_date_range(self, client):
        df = _make_df(30, start="2024-01-01")
        client.post("/api/v1/ohlcv", content=ArrowCodec().encode(df),
                    headers={"Content-Type": "application/vnd.apache.arrow.file",
                             "X-Symbol": "BTC", "X-Timeframe": "1d"})
        r = client.get("/api/v1/ohlcv",
                       params={"symbol": "BTC", "timeframe": "1d",
                               "start": "2024-01-10", "end": "2024-01-20"})
        assert r.status_code == 200
        df = ArrowCodec().decode(r.content)
        assert 8 <= len(df) <= 11

    def test_stats_endpoint(self, client):
        df = _make_df(5)
        client.post("/api/v1/ohlcv", content=ArrowCodec().encode(df),
                    headers={"Content-Type": "application/vnd.apache.arrow.file",
                             "X-Symbol": "BTC", "X-Timeframe": "1d"})
        r = client.get("/api/v1/ohlcv/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total_rows"] == 5


class TestOhlcvPost:
    def test_post_arrow(self, client):
        df = _make_df(10)
        arrow_bytes = ArrowCodec().encode(df)
        r = client.post("/api/v1/ohlcv", content=arrow_bytes,
                        headers={"Content-Type": "application/vnd.apache.arrow.file",
                                 "X-Symbol": "BTC", "X-Timeframe": "1d"})
        assert r.status_code == 200
        assert r.json()["rows_written"] == 10

    def test_post_json(self, client):
        records = _make_df(3).to_dict(orient="records")
        # 转 ISO 字符串
        for r in records:
            r["timestamp"] = r["timestamp"].isoformat()
        r = client.post("/api/v1/ohlcv", json=records,
                        headers={"Content-Type": "application/json",
                                 "X-Symbol": "BTC", "X-Timeframe": "1d"})
        assert r.status_code == 200
        assert r.json()["rows_written"] == 3

    def test_post_unsupported_content_type(self, client):
        r = client.post("/api/v1/ohlcv", content=b"x",
                        headers={"Content-Type": "text/plain",
                                 "X-Symbol": "BTC", "X-Timeframe": "1d"})
        assert r.status_code == 415

    def test_post_missing_symbol_header(self, client):
        r = client.post("/api/v1/ohlcv",
                        content=ArrowCodec().encode(_make_df(3)),
                        headers={"Content-Type": "application/vnd.apache.arrow.file",
                                 "X-Timeframe": "1d"})
        assert r.status_code == 422  # FastAPI 校验失败


class TestSymbolsEndpoint:
    def test_list_empty(self, client):
        r = client.get("/api/v1/symbols")
        assert r.status_code == 200
        assert r.json() == {"symbols": []}

    def test_list_after_ingest(self, client):
        df = _make_df(3)
        client.post("/api/v1/ohlcv", content=ArrowCodec().encode(df),
                    headers={"Content-Type": "application/vnd.apache.arrow.file",
                             "X-Symbol": "BTC", "X-Timeframe": "1d"})
        r = client.get("/api/v1/symbols")
        syms = r.json()["symbols"]
        assert "BTC" in syms

    def test_get_symbol_metadata_404(self, client):
        r = client.get("/api/v1/symbols/NOTEXIST")
        assert r.status_code == 404

    def test_get_symbol_metadata_ok(self, client):
        df = _make_df(3, start="2024-01-01")
        client.post("/api/v1/ohlcv", content=ArrowCodec().encode(df),
                    headers={"Content-Type": "application/vnd.apache.arrow.file",
                             "X-Symbol": "BTC", "X-Timeframe": "1d"})
        r = client.get("/api/v1/symbols/BTC")
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "BTC"
        assert data["first_seen"] is not None


class TestIngestEndpoint:
    def test_ingest_synthetic(self, client):
        r = client.post("/api/v1/ingest",
                        params={"symbol": "TEST", "timeframe": "1d",
                                "source": "synthetic"})
        assert r.status_code == 200
        data = r.json()
        assert data["rows_written"] > 0
        assert data["symbol"] == "TEST"

    def test_ingest_unknown_source(self, client):
        r = client.post("/api/v1/ingest",
                        params={"symbol": "X", "source": "nonexistent"})
        assert r.status_code == 400


class TestAppFactory:
    def test_app_creation(self, tmp_path):
        db = tmp_path / "x.db"
        config = Config(database_url=f"sqlite:///{db}")
        app = StorageApp.create(config)
        assert app.title == "StockStat Storage"
        assert hasattr(app.state, "storage_backend")

    def test_app_with_admin_enabled(self, tmp_path):
        db = tmp_path / "x.db"
        config = Config(database_url=f"sqlite:///{db}", admin_enabled=True)
        app = StorageApp.create(config)
        client = TestClient(app)
        r = client.get("/admin/api/health")
        assert r.status_code == 200

    def test_app_dispatcher_plugin_hook(self, tmp_path):
        db = tmp_path / "x.db"
        config = Config(database_url=f"sqlite:///{db}")
        called = []
        def mount_hook(app, **kw):
            called.append(("mount", app, kw.get("storage_backend")))
        app = StorageApp.create(config, dispatcher_plugin_mount=mount_hook)
        assert len(called) == 1
        assert called[0][2] is not None

    def test_app_state_has_backend(self, tmp_path):
        db = tmp_path / "x.db"
        config = Config(database_url=f"sqlite:///{db}")
        app = StorageApp.create(config)
        assert app.state.storage_backend is not None
        assert app.state.orm_session is not None
