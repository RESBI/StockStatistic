"""OHLCV REST API — /api/v1/ohlcv GET/POST。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request, Response, HTTPException, Header

from stockstat_foundation.codec import ArrowCodec

from ..storage.backend import StorageBackendImpl


def create_ohlcv_router(backend: StorageBackendImpl) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/ohlcv")
    async def get_ohlcv(
        symbol: str = Query(..., description="标的符号，逗号分隔多标的"),
        timeframe: str = Query("1d"),
        start: Optional[str] = Query(None),
        end: Optional[str] = Query(None),
        source: Optional[str] = Query(None),
        format: str = Query("arrow", description="arrow/json"),
    ):
        """查询 OHLCV 数据。"""
        symbols = [s.strip() for s in symbol.split(",") if s.strip()]
        df = backend.fetch_ohlcv(symbols, timeframe, start, end, source)

        # 多 symbol 返回 dict
        if isinstance(df, dict):
            import pandas as pd
            frames = []
            for sym, sub in df.items():
                if len(sub) > 0:
                    sub = sub.copy()
                    sub["symbol"] = sym
                    frames.append(sub)
            if not frames:
                raise HTTPException(404, "No data found")
            df = pd.concat(frames, ignore_index=True)

        if len(df) == 0:
            raise HTTPException(404, "No data found")

        if format == "json":
            return df.to_dict(orient="records")

        arrow_bytes = ArrowCodec().encode(df)
        return Response(
            content=arrow_bytes,
            media_type="application/vnd.apache.arrow.file",
        )

    @router.post("/api/v1/ohlcv")
    async def post_ohlcv(
        req: Request,
        x_symbol: str = Header(...),
        x_timeframe: str = Header(...),
    ):
        """写入 OHLCV 数据（请求体为 Arrow IPC 或 JSON）。"""
        body = await req.body()
        content_type = req.headers.get("content-type", "")

        if "arrow" in content_type:
            df = ArrowCodec().decode(body)
        elif "json" in content_type:
            import pandas as pd
            import json
            data = json.loads(body.decode("utf-8"))
            if isinstance(data, dict):
                data = [data]
            df = pd.DataFrame(data)
        else:
            raise HTTPException(415, f"Unsupported content-type: {content_type}")

        rows = backend.ingest_ohlcv(x_symbol, x_timeframe, df)
        return {"rows_written": rows, "symbol": x_symbol, "timeframe": x_timeframe}

    @router.get("/api/v1/ohlcv/stats")
    async def ohlcv_stats():
        """OHLCV 数据统计。"""
        return backend.stats()

    return router
