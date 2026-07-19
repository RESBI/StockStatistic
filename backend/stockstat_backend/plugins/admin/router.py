"""Admin API router — 15 management endpoints.

All endpoints are mounted under /admin/api/ and are independent
of the backend's main /api/v1/ routes.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .models import ensure_log_table, log_operation, IngestLog
from .utils import mask_db_url, get_disk_usage
from .lock import _ingest_lock, _batch_tasks


def create_admin_router() -> APIRouter:
    """Create the admin API router with all management endpoints."""
    router = APIRouter(prefix="/admin/api", tags=["admin"])

    # ── Health ────────────────────────────────────────────────

    @router.get("/health")
    async def admin_health():
        from stockstat_backend.config import settings
        from stockstat_backend.storage.database import get_engine
        from stockstat_backend.storage.cache import cache

        db_ok = True
        try:
            with get_engine().connect() as conn:
                conn.execute("SELECT 1")
        except Exception:
            db_ok = False

        return {
            "status": "ok" if db_ok else "degraded",
            "database": {
                "url": mask_db_url(settings.database_url),
                "connected": db_ok,
            },
            "cache": {
                "type": "memory",
                "ttl": settings.cache_ttl,
                "keys": len(cache._store) if hasattr(cache, "_store") else 0,
            },
            "proxy": settings.proxy.to_dict(),
        }

    # ── Config ────────────────────────────────────────────────

    @router.get("/config")
    async def admin_config():
        from stockstat_backend.config import settings
        return {
            "database_url": mask_db_url(settings.database_url),
            "redis_url": settings.redis_url or "(not configured)",
            "host": settings.host,
            "port": settings.port,
            "default_source": settings.default_source,
            "cache_ttl": settings.cache_ttl,
            "rate_limit": settings.rate_limit_per_minute,
            "proxy": settings.proxy.to_dict(),
            "admin_enabled": settings.admin_enabled,
        }

    # ── Proxy update (live) ───────────────────────────────────

    @router.put("/proxy")
    async def admin_update_proxy(enabled: bool = False, proxy_type: str = "http",
                                  url: str = ""):
        from stockstat_backend.config import settings, ProxyConfig
        from stockstat_backend.api.adapters import clear_adapters

        settings.proxy = ProxyConfig(
            enabled=enabled, proxy_type=proxy_type, url=url,
        )
        clear_adapters()
        log_operation("(config)", "proxy_change", status="success",
                       source=f"enabled={enabled},type={proxy_type}")
        return {"updated": True, "proxy": settings.proxy.to_dict()}

    # ── Cache ─────────────────────────────────────────────────

    @router.get("/cache")
    async def admin_cache_info():
        from stockstat_backend.storage.cache import cache
        return {
            "type": "memory",
            "ttl": 300,
            "keys": len(cache._store) if hasattr(cache, "_store") else 0,
        }

    @router.delete("/cache")
    async def admin_clear_cache():
        from stockstat_backend.storage.cache import cache
        cleared = len(cache._store) if hasattr(cache, "_store") else 0
        cache.clear()
        return {"cleared": True, "keys_removed": cleared}

    # ── Disk ──────────────────────────────────────────────────

    @router.get("/disk")
    async def admin_disk():
        from stockstat_backend.config import settings

        db_url = settings.database_url
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)
        else:
            db_path = os.getcwd()

        try:
            total, free, used = get_disk_usage(os.path.dirname(db_path) or ".")
            db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
            return {
                "total_gb": round(total / 1e9, 2),
                "used_gb": round(used / 1e9, 2),
                "free_gb": round(free / 1e9, 2),
                "used_percent": round(used / total * 100, 1) if total > 0 else 0,
                "db_file_size_mb": round(db_size / 1e6, 2),
                "db_path": db_path,
            }
        except Exception as e:
            return {
                "total_gb": 0, "used_gb": 0, "free_gb": 0,
                "used_percent": 0, "db_file_size_mb": 0,
                "db_path": db_path, "error": str(e),
            }

    # ── Symbols (local) ───────────────────────────────────────

    @router.get("/symbols")
    async def admin_symbols():
        from stockstat_backend.storage.repository import ohlcv_repo, symbol_repo
        from stockstat_backend.storage.database import get_session
        from stockstat_backend.models.ohlcv import OHLCV
        from sqlalchemy import select, func

        symbols = symbol_repo.list_symbols()
        result = []
        for s in symbols:
            sym = s["unified_symbol"]
            with get_session() as session:
                row_count = session.execute(
                    select(func.count()).select_from(OHLCV).where(OHLCV.symbol == sym)
                ).scalar()
                ts_result = session.execute(
                    select(func.min(OHLCV.ts), func.max(OHLCV.ts))
                    .where(OHLCV.symbol == sym)
                ).first()
                earliest = str(ts_result[0]) if ts_result and ts_result[0] else None
                latest = str(ts_result[1]) if ts_result and ts_result[1] else None
            result.append({
                **s,
                "row_count": row_count,
                "earliest": earliest,
                "latest": latest,
            })
        return {"count": len(result), "symbols": result}

    @router.delete("/symbols/{symbol:path}")
    async def admin_delete_symbol(symbol: str):
        from stockstat_backend.storage.repository import ohlcv_repo, symbol_repo
        from stockstat_backend.storage.cache import cache
        from stockstat_backend.models.ohlcv import OHLCV, SymbolRegistry
        from stockstat_backend.storage.database import get_session
        from sqlalchemy import delete as sql_delete

        with _ingest_lock:
            count = ohlcv_repo.count(symbol=symbol)
            with get_session() as session:
                session.execute(sql_delete(OHLCV).where(OHLCV.symbol == symbol))
            with get_session() as session:
                session.execute(sql_delete(SymbolRegistry).where(
                    SymbolRegistry.unified_symbol == symbol))
            cache.clear()
            log_operation(symbol, "delete", rows=-count)
        return {"deleted": True, "symbol": symbol, "rows_removed": count}

    # ── Sources ───────────────────────────────────────────────

    @router.get("/sources")
    async def admin_sources():
        return {
            "sources": [
                {"name": "yfinance", "type": "stock",
                 "description": "Yahoo Finance direct API"},
                {"name": "binance", "type": "crypto",
                 "description": "Binance via ccxt"},
                {"name": "coinbase", "type": "crypto",
                 "description": "Coinbase via ccxt"},
                {"name": "synthetic", "type": "mixed",
                 "description": "Synthetic data (offline testing)"},
            ]
        }

    @router.get("/sources/{source}/symbols")
    async def admin_source_symbols(source: str,
                                    page: int = Query(1, ge=1),
                                    size: int = Query(50, ge=1, le=200),
                                    search: str = ""):
        from stockstat_backend.api.adapters import get_adapter
        from stockstat_backend.storage.repository import symbol_repo

        try:
            adapter = get_adapter(source)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Cannot connect to source '{source}': {e}")

        try:
            all_symbols = adapter.fetch_symbols()
        except Exception as e:
            raise HTTPException(502, f"Failed to fetch symbols: {e}")

        if search:
            search_lower = search.lower()
            all_symbols = [s for s in all_symbols if search_lower in s.get("unified_symbol", "").lower()]

        local_set = set()
        try:
            for s in symbol_repo.list_symbols():
                local_set.add(s["unified_symbol"])
        except Exception:
            pass

        for s in all_symbols:
            s["downloaded"] = s.get("unified_symbol", "") in local_set

        total = len(all_symbols)
        start_idx = (page - 1) * size
        end_idx = start_idx + size
        page_items = all_symbols[start_idx:end_idx]

        return {
            "source": source,
            "page": page,
            "size": size,
            "total": total,
            "total_pages": (total + size - 1) // size,
            "symbols": page_items,
        }

    @router.get("/sources/{source}/info")
    async def admin_source_info(source: str, symbol: str = "",
                                 probe: bool = False, timeframe: str = "1d"):
        timeframes_by_source = {
            "binance": ["1s", "1m", "3m", "5m", "15m", "30m",
                        "1h", "2h", "4h", "6h", "8h", "12h",
                        "1d", "3d", "1w", "1M"],
            "coinbase": ["1m", "5m", "15m", "30m", "1h", "6h", "1d"],
            "yfinance": ["1m", "2m", "5m", "15m", "30m", "60m", "90m",
                         "1d", "5d", "1wk", "1mo", "3mo"],
            "synthetic": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"],
        }
        earliest_by_source = {
            "binance": "2017-08-17",
            "coinbase": "2015-01-01",
            "yfinance": "2010-01-01",
            "synthetic": "2020-01-01",
        }

        local_earliest = None
        local_latest = None
        if symbol:
            try:
                from stockstat_backend.storage.database import get_session
                from stockstat_backend.models.ohlcv import OHLCV
                from sqlalchemy import select, func
                with get_session() as session:
                    result = session.execute(
                        select(func.min(OHLCV.ts), func.max(OHLCV.ts))
                        .where(OHLCV.symbol == symbol)
                    ).first()
                    if result and result[0]:
                        local_earliest = str(result[0])
                        local_latest = str(result[1])
            except Exception:
                pass

        # Probe the source for the actual per-symbol time range
        probed_earliest = None
        probed_latest = None
        probe_error = None
        if probe and symbol:
            try:
                from stockstat_backend.api.adapters import get_adapter
                adapter = get_adapter(source)
                probed_earliest, probed_latest = adapter.probe_range(symbol, timeframe=timeframe)
            except Exception as e:
                probe_error = str(e)

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Use probed range if available, otherwise fall back to source-level defaults
        effective_earliest = probed_earliest or earliest_by_source.get(source, "2020-01-01")
        effective_latest = probed_latest or now

        return {
            "source": source,
            "symbol": symbol or None,
            "earliest_available": effective_earliest,
            "latest_available": effective_latest,
            "source_earliest_available": earliest_by_source.get(source, "2020-01-01"),
            "source_latest_available": now,
            "probed": probed_earliest is not None or probed_latest is not None,
            "probe_error": probe_error,
            "timeframes": timeframes_by_source.get(source, ["1d"]),
            "local_earliest": local_earliest,
            "local_latest": local_latest,
        }

    # ── Ingest ────────────────────────────────────────────────

    @router.post("/ingest")
    async def admin_ingest(symbol: str, source: Optional[str] = None,
                           start: Optional[str] = None, end: Optional[str] = None,
                           timeframe: str = "1d"):
        from stockstat_backend.api.adapters import get_adapter, auto_detect_source
        from stockstat_backend.normalizer.normalizer import normalize_ohlcv
        from stockstat_backend.storage.repository import ohlcv_repo, symbol_repo
        from stockstat_backend.storage.cache import cache

        src = source or auto_detect_source(symbol)
        try:
            adapter = get_adapter(src)
        except ValueError as e:
            raise HTTPException(400, str(e))

        if not adapter.supports(symbol):
            raise HTTPException(400, f"Source '{src}' does not support '{symbol}'")

        with _ingest_lock:
            try:
                df = adapter.fetch_ohlcv(symbol, start=start, end=end, timeframe=timeframe)
            except Exception as e:
                log_operation(symbol, "ingest", status="failed", error=str(e),
                               source=src, timeframe=timeframe)
                raise HTTPException(502, f"Fetch failed: {e}")

            if df.empty:
                log_operation(symbol, "ingest", status="failed", error="No data returned",
                               source=src, timeframe=timeframe)
                raise HTTPException(404, f"No data for {symbol}")

            rows = normalize_ohlcv(df, symbol, src, timeframe)
            count = ohlcv_repo.upsert_many(rows)

            if "/" in symbol:
                base, quote = symbol.split("/")
                symbol_repo.upsert(symbol, "crypto", base, quote, sources=src)
            else:
                symbol_repo.upsert(symbol, "stock", symbol, sources=src)

            cache.clear()
            log_operation(symbol, "ingest", rows=count, source=src, timeframe=timeframe)

        return {"symbol": symbol, "source": src, "ingested": count}

    @router.post("/ingest/batch")
    async def admin_batch_ingest(symbols: str, source: Optional[str] = None,
                                  start: Optional[str] = None, end: Optional[str] = None,
                                  timeframe: str = "1d"):
        symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
        if not symbol_list:
            raise HTTPException(400, "No symbols provided")

        batch_id = str(uuid.uuid4())[:8]
        _batch_tasks[batch_id] = {
            "total": len(symbol_list),
            "completed": 0,
            "current": symbol_list[0],
            "status": "running",
            "results": [],
        }

        def _run_batch():
            from stockstat_backend.api.adapters import get_adapter, auto_detect_source
            from stockstat_backend.normalizer.normalizer import normalize_ohlcv
            from stockstat_backend.storage.repository import ohlcv_repo, symbol_repo
            from stockstat_backend.storage.cache import cache

            for sym in symbol_list:
                task = _batch_tasks[batch_id]
                task["current"] = sym
                try:
                    src = source or auto_detect_source(sym)
                    adapter = get_adapter(src)
                    df = adapter.fetch_ohlcv(sym, start=start, end=end, timeframe=timeframe)
                    if df.empty:
                        task["results"].append({"symbol": sym, "status": "failed",
                                                "error": "No data"})
                        log_operation(sym, "batch_ingest", status="failed",
                                       error="No data", source=src, timeframe=timeframe)
                        continue
                    with _ingest_lock:
                        rows = normalize_ohlcv(df, sym, src, timeframe)
                        count = ohlcv_repo.upsert_many(rows)
                        if "/" in sym:
                            base, quote = sym.split("/")
                            symbol_repo.upsert(sym, "crypto", base, quote, sources=src)
                        else:
                            symbol_repo.upsert(sym, "stock", sym, sources=src)
                        cache.clear()
                    task["results"].append({"symbol": sym, "status": "success",
                                            "ingested": count})
                    log_operation(sym, "batch_ingest", rows=count,
                                   source=src, timeframe=timeframe)
                except Exception as e:
                    task["results"].append({"symbol": sym, "status": "failed",
                                            "error": str(e)})
                    log_operation(sym, "batch_ingest", status="failed", error=str(e))
                finally:
                    task["completed"] += 1

            _batch_tasks[batch_id]["status"] = "completed"

        thread = threading.Thread(target=_run_batch, daemon=True)
        thread.start()
        return {"batch_id": batch_id, "total": len(symbol_list)}

    @router.get("/ingest/progress/{batch_id}")
    async def admin_batch_progress(batch_id: str):
        task = _batch_tasks.get(batch_id)
        if task is None:
            raise HTTPException(404, "Batch task not found")
        return task

    # ── Stats ─────────────────────────────────────────────────

    @router.get("/stats")
    async def admin_stats():
        from stockstat_backend.storage.repository import ohlcv_repo, symbol_repo
        symbols = symbol_repo.list_symbols()
        total_rows = ohlcv_repo.count()
        per_source = {}
        for s in symbols:
            for src in s.get("sources", []):
                per_source[src] = per_source.get(src, 0) + 1
        return {
            "total_symbols": len(symbols),
            "total_rows": total_rows,
            "symbols_by_source": per_source,
        }

    # ── Logs ──────────────────────────────────────────────────

    @router.get("/logs")
    async def admin_logs(page: int = Query(1, ge=1),
                          size: int = Query(50, ge=1, le=200),
                          action: str = "", symbol: str = ""):
        ensure_log_table()
        try:
            from stockstat_backend.storage.database import get_session
            from sqlalchemy import select, desc, func

            with get_session() as session:
                stmt = select(IngestLog).order_by(desc(IngestLog.timestamp))
                if action:
                    stmt = stmt.where(IngestLog.action == action)
                if symbol:
                    stmt = stmt.where(IngestLog.symbol.contains(symbol))

                count_stmt = select(func.count()).select_from(IngestLog)
                if action:
                    count_stmt = count_stmt.where(IngestLog.action == action)
                if symbol:
                    count_stmt = count_stmt.where(IngestLog.symbol.contains(symbol))
                total = session.execute(count_stmt).scalar()

                stmt = stmt.offset((page - 1) * size).limit(size)
                rows = session.execute(stmt).scalars().all()

                return {
                    "page": page, "size": size,
                    "total": total,
                    "total_pages": (total + size - 1) // size,
                    "logs": [{
                        "timestamp": str(r.timestamp) if r.timestamp else "",
                        "symbol": r.symbol,
                        "action": r.action,
                        "rows_affected": r.rows_affected,
                        "status": r.status,
                        "error_message": r.error_message,
                        "source": r.source,
                        "timeframe": r.timeframe,
                    } for r in rows],
                }
        except Exception as e:
            return {"logs": [], "total": 0, "error": str(e)}

    # ── V3 Dispatcher monitoring (P7) ─────────────────────────

    @router.get("/dispatcher/cluster")
    async def admin_dispatcher_cluster():
        """V3 P7: cluster topology for Admin UI.

        Returns 404 if Dispatcher is not enabled.
        """
        from fastapi import HTTPException
        from stockstat_backend.app import app as _  # avoid circular import
        # We use the app's state, but routes are mounted on a different app.
        # Just re-create the dispatcher check via env var.
        import os
        if not os.environ.get("STOCKSTAT_DISPATCHER_ENABLED", "false").lower() in (
            "1", "true", "yes", "on"
        ):
            raise HTTPException(404, "Dispatcher not enabled")
        # Find the dispatcher via the app's state
        from stockstat_backend.config import settings
        # Use the FastAPI app's state where DispatcherPlugin.mount stored it
        # This is a bit hacky but works for the in-process case
        try:
            # The router was mounted on a specific app; we need to access it.
            # Use a module-level reference set by mount_admin_with_dispatcher.
            dispatcher = _DISPATCHER_REF[0]
            if dispatcher is None:
                raise HTTPException(404, "Dispatcher not registered")
            return dispatcher.cluster_info(include_offline=True)
        except Exception as e:
            raise HTTPException(500, f"Failed: {e}")

    @router.get("/dispatcher/tasks")
    async def admin_dispatcher_tasks(limit: int = Query(100, ge=1, le=1000),
                                       state: str = ""):
        """V3 P7: recent task history for Admin UI."""
        from fastapi import HTTPException
        dispatcher = _DISPATCHER_REF[0]
        if dispatcher is None:
            raise HTTPException(404, "Dispatcher not enabled")
        return {"history": dispatcher.get_task_history(
            limit=limit, state_filter=state or None,
        )}

    @router.get("/dispatcher/stats")
    async def admin_dispatcher_stats():
        """V3 P7: aggregate task stats for Admin UI dashboard."""
        from fastapi import HTTPException
        dispatcher = _DISPATCHER_REF[0]
        if dispatcher is None:
            raise HTTPException(404, "Dispatcher not enabled")
        return dispatcher.get_task_stats()

    @router.get("/dispatcher/autoscaler")
    async def admin_dispatcher_autoscaler():
        """V3 P7: Autoscaler metrics for Admin UI."""
        from fastapi import HTTPException
        dispatcher = _DISPATCHER_REF[0]
        if dispatcher is None:
            raise HTTPException(404, "Dispatcher not enabled")
        return dispatcher.get_autoscaler_metrics()

    return router


# Module-level reference for the Dispatcher (set when admin + dispatcher
# are mounted on the same app). This avoids circular imports.
_DISPATCHER_REF: list = [None]


def set_dispatcher_ref(dispatcher) -> None:
    """Set the Dispatcher reference for Admin UI access.

    Called by ``stockstat_backend.app.create_app`` when both admin and
    dispatcher are mounted on the same app.
    """
    _DISPATCHER_REF[0] = dispatcher
