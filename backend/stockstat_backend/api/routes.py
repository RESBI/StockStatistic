from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
import os

from ..adapters.yfinance import YFinanceAdapter
from ..adapters.yahoo_direct import YahooDirectAdapter
from ..adapters.ccxt_adapter import CcxtAdapter
from ..adapters.synthetic import SyntheticAdapter
from ..normalizer.normalizer import normalize_ohlcv
from ..storage.repository import ohlcv_repo, symbol_repo
from ..storage.cache import cache
from ..config import settings

router = APIRouter(prefix="/api/v1", tags=["ohlcv"])

_adapters = {}


def _get_adapter(source: str):
    if source not in _adapters:
        proxies = settings.proxy.proxies
        if source == "yfinance":
            _adapters[source] = YahooDirectAdapter(proxy=proxies)
        elif source == "binance":
            _adapters[source] = CcxtAdapter("binance", proxies=proxies)
        elif source == "coinbase":
            _adapters[source] = CcxtAdapter("coinbase", proxies=proxies)
        elif source == "synthetic":
            _adapters[source] = SyntheticAdapter()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown source: {source}")
    return _adapters[source]


def _auto_detect_source(symbol: str) -> str:
    if "/" in symbol:
        return "binance"
    return "yfinance"


@router.get("/health")
def health():
    return {"status": "ok", "proxy": settings.proxy.to_dict()}


@router.get("/sources")
def list_sources():
    return {
        "sources": [
            {"name": "yfinance", "type": "stock", "description": "US stocks / ETF via yfinance"},
            {"name": "binance", "type": "crypto", "description": "Binance via ccxt"},
            {"name": "coinbase", "type": "crypto", "description": "Coinbase via ccxt"},
            {"name": "synthetic", "type": "mixed", "description": "Synthetic data for offline testing"},
        ],
        "proxy": settings.proxy.to_dict(),
    }


@router.get("/proxy")
def get_proxy():
    return settings.proxy.to_dict()


@router.post("/ingest")
def ingest(
    symbol: str = Query(...),
    source: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    timeframe: str = Query("1d"),
):
    src = source or _auto_detect_source(symbol)
    adapter = _get_adapter(src)

    if not adapter.supports(symbol):
        raise HTTPException(
            status_code=400,
            detail=f"Source '{src}' does not support symbol '{symbol}'",
        )

    try:
        df = adapter.fetch_ohlcv(symbol, start=start, end=end, timeframe=timeframe)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fetch failed: {e}")

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    rows = normalize_ohlcv(df, symbol, src, timeframe)
    count = ohlcv_repo.upsert_many(rows)

    if "/" in symbol:
        base, quote = symbol.split("/")
        symbol_repo.upsert(symbol, "crypto", base, quote, sources=src)
    else:
        symbol_repo.upsert(symbol, "stock", symbol, sources=src)

    cache.clear()
    return {"symbol": symbol, "source": src, "ingested": count}


@router.get("/ohlcv")
def get_ohlcv(
    symbol: str = Query(...),
    source: Optional[str] = Query(None),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    timeframe: str = Query("1d"),
    limit: Optional[int] = Query(None),
    format: str = Query("json"),
):
    cached = cache.get(symbol, source, start, end, timeframe, limit)
    if cached is not None:
        return cached

    df = ohlcv_repo.query(
        symbol=symbol,
        source=source,
        start=start,
        end=end,
        timeframe=timeframe,
        limit=limit,
    )

    if df.empty:
        src = source or _auto_detect_source(symbol)
        raise HTTPException(
            status_code=404,
            detail=f"No data for '{symbol}'. Try POST /api/v1/ingest first.",
        )

    if format == "csv":
        from fastapi.responses import Response
        return Response(content=df.to_csv(), media_type="text/csv")

    data = []
    for ts, row in df.iterrows():
        data.append({
            "ts": ts.isoformat(),
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        })

    result = {
        "symbol": symbol,
        "source": source,
        "timeframe": timeframe,
        "count": len(data),
        "data": data,
    }
    cache.set(result, symbol, source, start, end, timeframe, limit)
    return result


@router.get("/symbols")
def list_symbols(asset_type: Optional[str] = Query(None)):
    return {"count": 0, "symbols": symbol_repo.list_symbols(asset_type)}


@router.get("/symbols/{symbol}")
def get_symbol(symbol: str):
    result = symbol_repo.get(symbol)
    if not result:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")
    return result
