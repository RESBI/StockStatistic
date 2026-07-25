"""
P0 Storage Backend Tests — real data via proxy.
Tests data ingestion and querying with real data sources (Yahoo Finance + Binance).
Proxy must be enabled and running at http://127.0.0.1:8889.
"""
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Enable proxy + real data sources
os.environ["STOCKSTAT_PROXY_ENABLED"] = "true"
os.environ["STOCKSTAT_PROXY_TYPE"] = "http"
os.environ["STOCKSTAT_PROXY_URL"] = "http://127.0.0.1:8889"
os.environ["DATABASE_URL"] = "sqlite:///test_backend_real.db"

from stockstat_backend.app import create_app
from stockstat_backend.storage.database import reset_engine, get_engine
from stockstat_backend.models.ohlcv import Base
from stockstat_backend.config import settings


@pytest.fixture(scope="module")
def client():
    settings.reload()
    reset_engine()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app = create_app()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["proxy"]["enabled"] is True


def test_proxy_config(client):
    resp = client.get("/api/v1/proxy")
    assert resp.status_code == 200
    proxy = resp.json()
    assert proxy["enabled"] is True
    assert "8889" in proxy["url"]


def test_sources(client):
    resp = client.get("/api/v1/sources")
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    names = [s["name"] for s in sources]
    assert "yfinance" in names
    assert "binance" in names


def test_ingest_yfinance(client):
    """Ingest AAPL via Yahoo Finance direct API through proxy"""
    resp = client.post("/api/v1/ingest", params={
        "symbol": "AAPL",
        "source": "yfinance",
        "start": "2024-01-01",
        "end": "2024-12-31",
        "timeframe": "1d",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["ingested"] > 200  # ~252 trading days


def test_ingest_ccxt_btc(client):
    """Ingest BTC/USDT via Binance/ccxt through proxy"""
    resp = client.post("/api/v1/ingest", params={
        "symbol": "BTC/USDT",
        "source": "binance",
        "start": "2024-01-01",
        "end": "2024-12-31",
        "timeframe": "1d",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTC/USDT"
    assert data["ingested"] > 300


def test_ingest_ccxt_eth(client):
    """Ingest ETH/USDT via Binance/ccxt"""
    resp = client.post("/api/v1/ingest", params={
        "symbol": "ETH/USDT",
        "source": "binance",
        "start": "2024-01-01",
        "end": "2024-12-31",
        "timeframe": "1d",
    })
    assert resp.status_code == 200
    assert resp.json()["ingested"] > 300


def test_ingest_ccxt_paxg(client):
    """Ingest PAXG/USDT (3 years for weekend correlation test)"""
    resp = client.post("/api/v1/ingest", params={
        "symbol": "PAXG/USDT",
        "source": "binance",
        "start": "2022-01-01",
        "end": "2024-12-31",
        "timeframe": "1d",
    })
    assert resp.status_code == 200
    assert resp.json()["ingested"] > 700


def test_ingest_yfinance_index(client):
    """Ingest ^GSPC (S&P 500 index) for Beta calculation"""
    resp = client.post("/api/v1/ingest", params={
        "symbol": "^GSPC",
        "source": "yfinance",
        "start": "2023-01-01",
        "end": "2024-12-31",
        "timeframe": "1d",
    })
    assert resp.status_code == 200
    assert resp.json()["ingested"] > 400


def test_query_ohlcv_json(client):
    resp = client.get("/api/v1/ohlcv", params={
        "symbol": "AAPL", "timeframe": "1d", "limit": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["count"] == 5
    row = data["data"][0]
    for field in ["open", "high", "low", "close", "volume"]:
        assert field in row


def test_query_ohlcv_csv(client):
    resp = client.get("/api/v1/ohlcv", params={
        "symbol": "BTC/USDT", "timeframe": "1d", "limit": 3, "format": "csv",
    })
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    lines = resp.text.strip().split("\n")
    assert len(lines) == 4  # header + 3 rows


def test_query_date_filter(client):
    resp = client.get("/api/v1/ohlcv", params={
        "symbol": "BTC/USDT",
        "start": "2024-06-01", "end": "2024-06-30",
        "timeframe": "1d",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert 20 <= data["count"] <= 31


def test_query_not_found(client):
    resp = client.get("/api/v1/ohlcv", params={"symbol": "NONEXIST/USDT"})
    assert resp.status_code == 404


def test_query_cache(client):
    params = {"symbol": "AAPL", "limit": 10}
    t1 = time.time()
    client.get("/api/v1/ohlcv", params=params)
    first = time.time() - t1
    t2 = time.time()
    client.get("/api/v1/ohlcv", params=params)
    second = time.time() - t2
    assert second <= first


def test_symbols(client):
    resp = client.get("/api/v1/symbols")
    assert resp.status_code == 200
    symbols = resp.json()["symbols"]
    names = [s["unified_symbol"] for s in symbols]
    assert "AAPL" in names
    assert "BTC/USDT" in names
    assert "PAXG/USDT" in names


def test_auto_detect_source(client):
    """Auto-detect should pick yfinance for stocks, binance for crypto"""
    resp = client.post("/api/v1/ingest", params={
        "symbol": "MSFT",
        "start": "2024-01-01",
        "end": "2024-06-30",
        "timeframe": "1d",
    })
    assert resp.status_code == 200
    assert resp.json()["source"] == "yfinance"
