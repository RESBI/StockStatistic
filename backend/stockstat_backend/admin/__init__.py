"""Web admin interface plugin for StockStat storage backend.

Provides a full-featured management UI at /admin/ with:
- Dashboard (overview, stats, data coverage gantt)
- Source Browser (browse remote directories, search, batch download)
- Local Symbols (K-line chart, range select, data preview, delete)
- Settings (DB path, proxy live-update, cache, disk)
- Logs (ingest history with filtering)

Request conflict handling:
- Ingest operations are serialized via a threading.Lock to prevent
  concurrent writes to the same symbol (SQLite limitation).
- Proxy config update clears the adapter cache atomically.
- Batch ingest uses a background thread + SSE for progress without
  blocking the main event loop.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, PrimaryKeyConstraint
from sqlalchemy.orm import DeclarativeBase

# ── Ingest log model ──────────────────────────────────────────

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


_log_table_created = False
_ingest_lock = threading.Lock()
_batch_tasks: dict[str, dict] = {}  # batch_id → {total, completed, current, status, results}


def _ensure_log_table():
    """Create the ingest log table if it doesn't exist."""
    global _log_table_created
    if _log_table_created:
        return
    try:
        from stockstat_backend.storage.database import get_engine
        _AdminBase.metadata.create_all(get_engine())
        _log_table_created = True
    except Exception:
        pass  # Backend not available


def _log_operation(symbol: str, action: str, rows: int = 0,
                   status: str = "success", error: str = None,
                   source: str = None, timeframe: str = None):
    """Write an entry to the ingest log."""
    try:
        from stockstat_backend.storage.database import get_session
        _ensure_log_table()
        with get_session() as session:
            session.add(IngestLog(
                symbol=symbol, action=action, rows_affected=rows,
                status=status, error_message=error,
                source=source, timeframe=timeframe,
            ))
    except Exception:
        pass  # Logging is best-effort


def _mask_db_url(url: str) -> str:
    """Mask password in database URL for display."""
    if "@" in url and "://" in url:
        scheme = url.split("://")[0]
        rest = url.split("://", 1)[1]
        if ":" in rest.split("@")[0]:
            user = rest.split(":")[0]
            return f"{scheme}://{user}:***@{rest.split('@', 1)[1]}"
    return url


# ═══════════════════════════════════════════════════════════════
# API Router
# ═══════════════════════════════════════════════════════════════

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
                "url": _mask_db_url(settings.database_url),
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
            "database_url": _mask_db_url(settings.database_url),
            "redis_url": settings.redis_url or "(not configured)",
            "host": settings.host,
            "port": settings.port,
            "default_source": settings.default_source,
            "cache_ttl": settings.cache_ttl,
            "rate_limit": settings.rate_limit_per_minute,
            "proxy": settings.proxy.to_dict(),
        }

    # ── Proxy update (live) ───────────────────────────────────

    @router.put("/proxy")
    async def admin_update_proxy(enabled: bool = False, proxy_type: str = "http",
                                  url: str = ""):
        """Update proxy configuration. Takes effect immediately."""
        from stockstat_backend.config import settings, ProxyConfig
        from stockstat_backend.api.routes import _adapters

        settings.proxy = ProxyConfig(
            enabled=enabled, proxy_type=proxy_type, url=url,
        )
        # Clear cached adapters so they rebuild with new proxy
        _adapters.clear()
        _log_operation("(config)", "proxy_change", status="success",
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
        """Get disk space info for the database location."""
        from stockstat_backend.config import settings
        import pathlib

        # Determine db file path
        db_url = settings.database_url
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)
        else:
            db_path = os.getcwd()

        try:
            stat = os.statvfs(os.path.dirname(db_path) or ".")
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            used = total - free
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
            return {"error": str(e)}

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
                # Get earliest and latest in one query
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
        """Delete all OHLCV data for a symbol. Serialized to prevent conflicts."""
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
            _log_operation(symbol, "delete", rows=-count)
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
        """Browse a data source's symbol directory with pagination."""
        from stockstat_backend.api.routes import _get_adapter
        from stockstat_backend.storage.repository import symbol_repo

        try:
            adapter = _get_adapter(source)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Cannot connect to source '{source}': {e}")

        # Fetch all symbols from the source
        try:
            all_symbols = adapter.fetch_symbols()
        except Exception as e:
            raise HTTPException(502, f"Failed to fetch symbols: {e}")

        # Filter by search
        if search:
            search_lower = search.lower()
            all_symbols = [s for s in all_symbols if search_lower in s.get("unified_symbol", "").lower()]

        # Get local symbols for "downloaded" status
        local_set = set()
        try:
            for s in symbol_repo.list_symbols():
                local_set.add(s["unified_symbol"])
        except Exception:
            pass

        for s in all_symbols:
            s["downloaded"] = s.get("unified_symbol", "") in local_set

        # Paginate
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

    # ── Ingest ────────────────────────────────────────────────

    @router.post("/ingest")
    async def admin_ingest(symbol: str, source: Optional[str] = None,
                           start: Optional[str] = None, end: Optional[str] = None,
                           timeframe: str = "1d"):
        """Trigger data ingestion. Serialized to prevent concurrent write conflicts."""
        from stockstat_backend.api.routes import _get_adapter, _auto_detect_source
        from stockstat_backend.normalizer.normalizer import normalize_ohlcv
        from stockstat_backend.storage.repository import ohlcv_repo, symbol_repo
        from stockstat_backend.storage.cache import cache

        src = source or _auto_detect_source(symbol)
        adapter = _get_adapter(src)

        if not adapter.supports(symbol):
            raise HTTPException(400, f"Source '{src}' does not support '{symbol}'")

        with _ingest_lock:
            try:
                df = adapter.fetch_ohlcv(symbol, start=start, end=end, timeframe=timeframe)
            except Exception as e:
                _log_operation(symbol, "ingest", status="failed", error=str(e),
                               source=src, timeframe=timeframe)
                raise HTTPException(502, f"Fetch failed: {e}")

            if df.empty:
                _log_operation(symbol, "ingest", status="failed", error="No data returned",
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
            _log_operation(symbol, "ingest", rows=count, source=src, timeframe=timeframe)

        return {"symbol": symbol, "source": src, "ingested": count}

    @router.post("/ingest/batch")
    async def admin_batch_ingest(symbols: str, source: Optional[str] = None,
                                  start: Optional[str] = None, end: Optional[str] = None,
                                  timeframe: str = "1d"):
        """Start a batch ingest task. Returns batch_id for progress tracking."""
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

        # Run in background thread
        def _run_batch():
            from stockstat_backend.api.routes import _get_adapter, _auto_detect_source
            from stockstat_backend.normalizer.normalizer import normalize_ohlcv
            from stockstat_backend.storage.repository import ohlcv_repo, symbol_repo
            from stockstat_backend.storage.cache import cache

            for sym in symbol_list:
                task = _batch_tasks[batch_id]
                task["current"] = sym
                try:
                    src = source or _auto_detect_source(sym)
                    adapter = _get_adapter(src)
                    df = adapter.fetch_ohlcv(sym, start=start, end=end, timeframe=timeframe)
                    if df.empty:
                        task["results"].append({"symbol": sym, "status": "failed",
                                                "error": "No data"})
                        _log_operation(sym, "batch_ingest", status="failed",
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
                    _log_operation(sym, "batch_ingest", rows=count,
                                   source=src, timeframe=timeframe)
                except Exception as e:
                    task["results"].append({"symbol": sym, "status": "failed",
                                            "error": str(e)})
                    _log_operation(sym, "batch_ingest", status="failed", error=str(e))
                finally:
                    task["completed"] += 1

            _batch_tasks[batch_id]["status"] = "completed"

        thread = threading.Thread(target=_run_batch, daemon=True)
        thread.start()
        return {"batch_id": batch_id, "total": len(symbol_list)}

    @router.get("/ingest/progress/{batch_id}")
    async def admin_batch_progress(batch_id: str):
        """Get batch ingest progress (poll-based; client can also use SSE)."""
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
        """Query ingest history logs with filtering."""
        _ensure_log_table()
        try:
            from stockstat_backend.storage.database import get_session
            from sqlalchemy import select, desc, func

            with get_session() as session:
                stmt = select(IngestLog).order_by(desc(IngestLog.timestamp))
                if action:
                    stmt = stmt.where(IngestLog.action == action)
                if symbol:
                    stmt = stmt.where(IngestLog.symbol.contains(symbol))

                # Count total
                count_stmt = select(func.count()).select_from(IngestLog)
                if action:
                    count_stmt = count_stmt.where(IngestLog.action == action)
                if symbol:
                    count_stmt = count_stmt.where(IngestLog.symbol.contains(symbol))
                total = session.execute(count_stmt).scalar()

                # Paginate
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

    return router


# ═══════════════════════════════════════════════════════════════
# Static Web UI — Full SPA
# ═══════════════════════════════════════════════════════════════

def mount_admin(app) -> None:
    """Mount the admin router and static UI on a FastAPI app."""
    router = create_admin_router()
    app.include_router(router)

    @app.get("/admin", response_class=HTMLResponse)
    @app.get("/admin/", response_class=HTMLResponse)
    async def admin_ui():
        return HTMLResponse(content=_ADMIN_HTML)


_ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StockStat Storage Admin</title>
<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f1419;color:#e0e0e0;display:flex;height:100vh;overflow:hidden}
.sidebar{width:200px;background:#1a2332;border-right:2px solid #2a3f5f;display:flex;flex-direction:column;padding:0}
.sidebar .logo{padding:16px 20px;border-bottom:2px solid #2a3f5f;font-size:16px;color:#4fc3f7;font-weight:700;cursor:pointer}
.nav-item{padding:12px 20px;cursor:pointer;color:#aaa;font-size:14px;border-left:3px solid transparent;transition:all .15s}
.nav-item:hover{background:#243447;color:#e0e0e0}
.nav-item.active{background:#243447;color:#4fc3f7;border-left-color:#4fc3f7}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.topbar{background:#1a2332;padding:10px 24px;border-bottom:2px solid #2a3f5f;display:flex;justify-content:space-between;align-items:center}
.topbar .status{font-size:13px}
.ok{color:#66bb6a}.bad{color:#ef5350}.warn{color:#ffa726}
.content{flex:1;overflow-y:auto;padding:24px}
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-bottom:24px}
.stat-card{background:#1a2332;padding:16px;border-radius:8px;text-align:center;border:1px solid #2a3f5f}
.stat-card .num{font-size:28px;font-weight:bold;color:#4fc3f7}
.stat-card .label{font-size:12px;color:#aaa;margin-top:4px}
.section{background:#1a2332;border:1px solid #2a3f5f;border-radius:8px;padding:20px;margin-bottom:20px}
.section h3{color:#4fc3f7;margin-bottom:12px;font-size:15px}
table{width:100%;border-collapse:collapse}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #2a3f5f;font-size:13px}
th{color:#4fc3f7;font-weight:600}
tr:hover{background:#243447}
.btn{padding:6px 14px;background:#2a6496;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px}
.btn:hover{background:#3a7ab6}
.btn.danger{background:#c0392b}.btn.danger:hover{background:#e74c3c}
.btn.success{background:#27ae60}.btn.success:hover{background:#2ecc71}
.btn.small{padding:3px 10px;font-size:12px}
input,select{padding:6px 10px;background:#0f1419;color:#e0e0e0;border:1px solid #2a3f5f;border-radius:4px;font-size:13px}
.row{display:flex;gap:8px;margin-bottom:12px;align-items:center;flex-wrap:wrap}
.row label{min-width:70px;font-size:13px;color:#aaa}
.split{display:flex;gap:16px;height:calc(100vh - 160px)}
.split-left{width:240px;overflow-y:auto;background:#1a2332;border:1px solid #2a3f5f;border-radius:8px}
.split-right{flex:1;overflow-y:auto}
.sym-item{padding:10px 14px;cursor:pointer;border-bottom:1px solid #2a3f5f;font-size:13px;display:flex;justify-content:space-between;align-items:center}
.sym-item:hover{background:#243447}
.sym-item.active{background:#243447;color:#4fc3f7;border-left:3px solid #4fc3f7}
.badge{font-size:11px;padding:2px 6px;border-radius:3px}
.badge.downloaded{background:#1b3a2a;color:#66bb6a}
.badge.missing{background:#3a3520;color:#ffa726}
.chart-container{background:#1a2332;border:1px solid #2a3f5f;border-radius:8px;padding:16px;margin-bottom:16px}
.gantt-row{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px}
.gantt-bar{height:14px;background:#2a6496;border-radius:3px;min-width:2px}
.gantt-label{width:100px;color:#aaa;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.progress-bar{height:20px;background:#0f1419;border-radius:4px;overflow:hidden;margin:8px 0}
.progress-fill{height:100%;background:#27ae60;transition:width .3s}
.msg{padding:8px 16px;border-radius:4px;margin:8px 0;font-size:13px}
.msg.ok{background:#1b3a2a;color:#66bb6a}.msg.err{background:#3a1b1b;color:#ef5350}
.pagination{display:flex;gap:4px;align-items:center;justify-content:center;margin-top:12px}
.pagination a{padding:4px 10px;background:#1a2332;border:1px solid #2a3f5f;border-radius:4px;cursor:pointer;font-size:13px}
.pagination a.active{background:#2a6496;color:#fff}
.switch{position:relative;width:40px;height:20px;background:#333;border-radius:10px;cursor:pointer}
.switch.on{background:#27ae60}
.switch::after{content:'';position:absolute;top:2px;left:2px;width:16px;height:16px;background:#fff;border-radius:50%;transition:.2s}
.switch.on::after{left:22px}
.checkbox{width:16px;height:16px;accent-color:#4fc3f7}
.batch-bar{position:sticky;bottom:0;background:#1a2332;border:1px solid #2a3f5f;border-radius:8px;padding:12px;margin-top:12px}
</style>
</head>
<body>
<div class="sidebar">
  <div class="logo" onclick="navigate('dashboard')">📈 StockStat</div>
  <div class="nav-item active" data-page="dashboard" onclick="navigate('dashboard')">📊 概览</div>
  <div class="nav-item" data-page="source" onclick="navigate('source')">📁 数据源浏览</div>
  <div class="nav-item" data-page="local" onclick="navigate('local')">💾 本地标的</div>
  <div class="nav-item" data-page="config" onclick="navigate('config')">⚙ 配置</div>
  <div class="nav-item" data-page="logs" onclick="navigate('logs')">📋 日志</div>
</div>
<div class="main">
  <div class="topbar">
    <div id="page-title">概览</div>
    <div class="status" id="hdr-status">Loading...</div>
  </div>
  <div class="content" id="content"></div>
</div>

<script>
const API='/admin/api';
let chartInstance=null;
let currentSymbol=null;
let healthTimer=null;

// ── Utils ──────────────────────────────────────────────────
async function api(path,opts){
  const r=await fetch(API+path,opts);
  if(!r.ok){const e=await r.json().catch(()=>({detail:r.statusText}));throw new Error(e.detail||r.status)}
  return r.json();
}
function fmt(n){return (n||0).toLocaleString()}
function esc(s){return String(s||'').replace(/</g,'&lt;')}
function shortDate(s){return s?s.split('T')[0]:''}

// ── Navigation ─────────────────────────────────────────────
function navigate(page,params={}){
  document.querySelectorAll('.nav-item').forEach(e=>e.classList.remove('active'));
  const el=document.querySelector(`[data-page="${page}"]`);
  if(el)el.classList.add('active');
  const titles={dashboard:'📊 概览',source:'📁 数据源浏览',local:'💾 本地标的',config:'⚙ 配置',logs:'📋 日志'};
  document.getElementById('page-title').textContent=titles[page]||page;
  const pages={dashboard:renderDashboard,source:renderSource,local:renderLocal,config:renderConfig,logs:renderLogs};
  if(pages[page])pages[page](params);
}
function startHealthCheck(){
  if(healthTimer)clearInterval(healthTimer);
  healthTimer=setInterval(async()=>{
    try{const h=await api('/health');
      const cls=h.status==='ok'?'ok':'bad';
      document.getElementById('hdr-status').innerHTML=`<span class="${cls}">● ${h.status.toUpperCase()}</span>`;
    }catch{document.getElementById('hdr-status').innerHTML='<span class="bad">● OFFLINE</span>'}
  },10000);
  // Also fire immediately
  (async()=>{try{const h=await api('/health');
    document.getElementById('hdr-status').innerHTML=`<span class="${h.status==='ok'?'ok':'bad'}">● ${h.status.toUpperCase()}</span>`;
  }catch{document.getElementById('hdr-status').innerHTML='<span class="bad">● OFFLINE</span>'}})()
}

// ── Dashboard ──────────────────────────────────────────────
async function renderDashboard(){
  const c=document.getElementById('content');
  c.innerHTML='<div class="stats" id="d-stats"></div><div class="section"><h3>数据覆盖时间轴</h3><div id="d-gantt"></div></div><div class="section"><h3>最近采集记录</h3><div id="d-logs"></div></div>';
  try{
    const[stats,symbols,logs,health,disk]=await Promise.all([
      api('/stats'),api('/symbols'),api('/logs?size=5'),api('/health'),api('/disk')
    ]);
    // Stat cards
    document.getElementById('d-stats').innerHTML=`
      <div class="stat-card"><div class="num">${stats.total_symbols}</div><div class="label">已下标的</div></div>
      <div class="stat-card"><div class="num">${fmt(stats.total_rows)}</div><div class="label">总行数</div></div>
      <div class="stat-card"><div class="num">${disk.db_file_size_mb||'-'} MB</div><div class="label">数据库大小</div></div>
      <div class="stat-card"><div class="num">${disk.used_percent||'-'}%</div><div class="label">磁盘使用率</div></div>`;
    // Source distribution
    let distHtml='<div style="margin-top:8px">';
    for(const[k,v]of Object.entries(stats.symbols_by_source||{}))
      distHtml+=`<div style="margin:4px 0">${k}: ${v} (${Math.round(v/stats.total_symbols*100)}%) ${'█'.repeat(Math.round(v/stats.total_symbols*20))}</div>`;
    distHtml+='</div>';
    document.getElementById('d-stats').innerHTML+=`<div class="stat-card" style="grid-column:span 2"><div class="num" style="font-size:14px;text-align:left">按数据源分布</div>${distHtml}</div>`;
    // Gantt chart
    if(symbols.symbols.length>0){
      const allDates=symbols.symbols.flatMap(s=>[s.earliest,s.latest].filter(Boolean));
      const minD=Math.min(...allDates.map(d=>new Date(d).getTime()));
      const maxD=Math.max(...allDates.map(d=>new Date(d).getTime()));
      const range=maxD-minD||1;
      let ganttHtml='';
      for(const s of symbols.symbols){
        if(!s.earliest||!s.latest)continue;
        const startPct=(new Date(s.earliest).getTime()-minD)/range*100;
        const widthPct=(new Date(s.latest).getTime()-new Date(s.earliest).getTime())/range*100;
        ganttHtml+=`<div class="gantt-row"><div class="gantt-label" title="${s.unified_symbol}">${s.unified_symbol}</div><div style="flex:1;position:relative"><div class="gantt-bar" style="margin-left:${startPct}%;width:${Math.max(widthPct,1)}%" onclick="navigate('local',{symbol:'${s.unified_symbol}'})"></div></div><div style="width:80px;font-size:11px;color:#888">${shortDate(s.earliest)}~${shortDate(s.latest)}</div></div>`;
      }
      document.getElementById('d-gantt').innerHTML=ganttHtml;
    }else{document.getElementById('d-gantt').innerHTML='<p style="color:#888">暂无数据</p>'}
    // Recent logs
    if(logs.logs&&logs.logs.length>0){
      document.getElementById('d-logs').innerHTML=`<table><thead><tr><th>时间</th><th>标的</th><th>操作</th><th>行数</th><th>状态</th></tr></thead><tbody>${logs.logs.map(l=>`<tr><td>${shortDate(l.timestamp)} ${l.timestamp.split('T')[1]?.split('.')[0]||''}</td><td>${esc(l.symbol)}</td><td>${l.action}</td><td>${l.rows_affected}</td><td>${l.status==='success'?'✅':'❌'}</td></tr>`).join('')}</tbody></table>`;
    }else{document.getElementById('d-logs').innerHTML='<p style="color:#888">暂无记录</p>'}
  }catch(e){c.innerHTML=`<div class="msg err">Error: ${e}</div>`}
}

// ── Source Browser ─────────────────────────────────────────
let srcState={source:'binance',page:1,search:'',selected:new Set()};
async function renderSource(){
  const c=document.getElementById('content');
  c.innerHTML=`
    <div class="row">
      <label>数据源</label><select id="src-select" onchange="srcState.source=this.value;srcState.page=1;loadSourceSymbols()">
        <option value="binance">Binance</option><option value="coinbase">Coinbase</option>
        <option value="yfinance">yfinance</option><option value="synthetic">Synthetic</option>
      </select>
      <label>搜索</label><input id="src-search" placeholder="BTC, ETH..." oninput="srcState.search=this.value;srcState.page=1;loadSourceSymbols()">
    </div>
    <div class="section">
      <table><thead><tr><th><input type="checkbox" class="checkbox" onchange="document.querySelectorAll('.src-check').forEach(c=>{c.checked=this.checked;toggleSelect(c.value,this.checked)})"></th><th>标的</th><th>类型</th><th>已下载</th><th>操作</th></tr></thead>
      <tbody id="src-body"></tbody></table>
      <div id="src-pager"></div>
    </div>
    <div class="batch-bar" id="batch-bar" style="display:none">
      <span id="batch-info"></span>
      <div class="row" style="margin-top:8px">
        <label>开始</label><input type="date" id="batch-start" value="2024-01-01">
        <label>结束</label><input type="date" id="batch-end" value="2024-12-31">
        <label>粒度</label><select id="batch-tf"><option>1d</option><option>1h</option><option>4h</option></select>
        <button class="btn success" onclick="doBatchIngest()">批量下载</button>
      </div>
      <div id="batch-progress"></div>
    </div>`;
  document.getElementById('src-select').value=srcState.source;
  document.getElementById('src-search').value=srcState.search;
  loadSourceSymbols();
}
function toggleSelect(sym,checked){
  if(checked)srcState.selected.add(sym);else srcState.selected.delete(sym);
  updateBatchBar();
}
function updateBatchBar(){
  const bar=document.getElementById('batch-bar');
  if(!bar)return;
  if(srcState.selected.size>0){bar.style.display='block';
    document.getElementById('batch-info').textContent=`已选 ${srcState.selected.size} 个标的`;}
  else bar.style.display='none';
}
async function loadSourceSymbols(){
  const body=document.getElementById('src-body');
  body.innerHTML='<tr><td colspan="5" style="text-align:center;color:#888">加载中...</td></tr>';
  try{
    const params=`?page=${srcState.page}&size=50&search=${encodeURIComponent(srcState.search)}`;
    const data=await api(`/sources/${srcState.source}/symbols${params}`);
    if(data.symbols.length===0){body.innerHTML='<tr><td colspan="5" style="text-align:center;color:#888">无匹配标的</td></tr>';return}
    body.innerHTML=data.symbols.map(s=>`<tr>
      <td><input type="checkbox" class="checkbox src-check" value="${s.unified_symbol}" ${srcState.selected.has(s.unified_symbol)?'checked':''} onchange="toggleSelect(this.value,this.checked)"></td>
      <td>${esc(s.unified_symbol)}</td><td>${s.asset_type||''}</td>
      <td>${s.downloaded?'<span class="badge downloaded">✅ 已下载</span>':'<span class="badge missing">—</span>'}</td>
      <td>${s.downloaded?`<button class="btn small" onclick="quickIngest('${s.unified_symbol}','${srcState.source}')">补全</button> <button class="btn small" onclick="navigate('local',{symbol:'${s.unified_symbol}'})">查看</button>`:`<button class="btn small success" onclick="quickIngest('${s.unified_symbol}','${srcState.source}')">下载</button>`}</td>
    </tr>`).join('');
    // Pagination
    const pager=document.getElementById('src-pager');
    if(data.total_pages>1){
      let html='<div class="pagination">';
      for(let i=1;i<=Math.min(data.total_pages,10);i++)
        html+=`<a class="${i===srcState.page?'active':''}" onclick="srcState.page=${i};loadSourceSymbols()">${i}</a>`;
      if(data.total_pages>10)html+=`<span>... ${data.total_pages} pages</span>`;
      html+='</div>';
      pager.innerHTML=html;
    }else pager.innerHTML='';
  }catch(e){body.innerHTML=`<tr><td colspan="5" class="msg err">Error: ${e}</td></tr>`}
}
async function quickIngest(sym,src){
  if(!confirm(`下载 ${sym} 从 ${src}？`))return;
  try{const r=await api(`/ingest?symbol=${encodeURIComponent(sym)}&source=${src}`, {method:'POST'});
    alert(`完成: ${r.ingested} 行`);loadSourceSymbols();}
  catch(e){alert(`失败: ${e}`)}
}
async function doBatchIngest(){
  const syms=[...srcState.selected].join(',');
  const start=document.getElementById('batch-start').value;
  const end=document.getElementById('batch-end').value;
  const tf=document.getElementById('batch-tf').value;
  const prog=document.getElementById('batch-progress');
  prog.innerHTML='<div class="msg">提交中...</div>';
  try{
    const r=await api(`/ingest/batch?symbols=${encodeURIComponent(syms)}&start=${start}&end=${end}&timeframe=${tf}`,{method:'POST'});
    // Poll progress
    const poll=async()=>{
      const p=await api(`/ingest/progress/${r.batch_id}`);
      const pct=Math.round(p.completed/p.total*100);
      prog.innerHTML=`<div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div><div style="font-size:13px">${p.completed}/${p.total} — ${p.current} ${p.results.length?p.results[p.results.length-1].status:''}</div>`;
      if(p.status==='completed'){
        prog.innerHTML+=`<div class="msg ok">批量下载完成</div>`;
        srcState.selected.clear();updateBatchBar();loadSourceSymbols();
      }else setTimeout(poll,1000);
    };
    poll();
  }catch(e){prog.innerHTML=`<div class="msg err">Error: ${e}</div>`}
}

// ── Local Symbols ──────────────────────────────────────────
async function renderLocal(params={}){
  if(params.symbol){currentSymbol=params.symbol}
  const c=document.getElementById('content');
  c.innerHTML=`<div class="split">
    <div class="split-left" id="local-list"><div style="padding:12px"><input id="local-search" placeholder="搜索..." oninput="filterLocal(this.value)" style="width:100%"></div><div id="local-items"></div></div>
    <div class="split-right" id="local-detail"><div style="padding:40px;color:#888">选择左侧标的查看详情</div></div>
  </div>`;
  try{
    const data=await api('/symbols');
    window._localSymbols=data.symbols;
    renderLocalList(data.symbols);
    if(currentSymbol)selectSymbol(currentSymbol);
  }catch(e){document.getElementById('local-items').innerHTML=`<div class="msg err">${e}</div>`}
}
function renderLocalList(symbols){
  document.getElementById('local-items').innerHTML=symbols.map(s=>
    `<div class="sym-item ${s.unified_symbol===currentSymbol?'active':''}" onclick="selectSymbol('${s.unified_symbol}')">
      <span>${esc(s.unified_symbol)}</span><span class="badge downloaded">✅</span>
    </div>`).join('');
}
function filterLocal(q){
  const filtered=window._localSymbols.filter(s=>s.unified_symbol.toLowerCase().includes(q.toLowerCase()));
  renderLocalList(filtered);
}
async function selectSymbol(sym){
  currentSymbol=sym;
  document.querySelectorAll('.sym-item').forEach(e=>e.classList.remove('active'));
  // Re-render list to update active state
  renderLocalList(window._localSymbols);
  const detail=document.getElementById('local-detail');
  detail.innerHTML='<div style="padding:20px;color:#888">加载中...</div>';
  try{
    const symInfo=window._localSymbols.find(s=>s.unified_symbol===sym)||{};
    const ohlcv=await fetch(`/api/v1/ohlcv?symbol=${encodeURIComponent(sym)}&limit=200`).then(r=>r.json());
    const rows=ohlcv.data||[];
    detail.innerHTML=`
      <div style="padding:0 0 12px"><strong style="font-size:18px;color:#4fc3f7">${esc(sym)}</strong>
      <span style="color:#888;margin-left:12px">${symInfo.asset_type||''} · ${symInfo.sources?.join(', ')||''} · ${fmt(symInfo.row_count)}行</span>
      <span style="color:#888;margin-left:12px">${shortDate(symInfo.earliest)} ~ ${shortDate(symInfo.latest)}</span></div>
      <div class="chart-container"><div id="chart" style="height:400px"></div></div>
      <div class="row"><span style="color:#888">截选范围:</span><input type="date" id="range-start"><span>~</span><input type="date" id="range-end">
        <button class="btn small" onclick="rangeIngest('${esc(sym)}')">补全此范围</button>
        <button class="btn small" onclick="rangeExport('${esc(sym)}')">导出CSV</button>
      </div>
      <div class="section"><h3>数据预览 (最近 20 行)</h3>
        <table><thead><tr><th>时间</th><th>开</th><th>高</th><th>低</th><th>收</th><th>量</th></tr></thead>
        <tbody>${rows.slice(-20).reverse().map(r=>`<tr><td>${shortDate(r.ts)}</td><td>${r.open.toFixed(2)}</td><td>${r.high.toFixed(2)}</td><td>${r.low.toFixed(2)}</td><td>${r.close.toFixed(2)}</td><td>${fmt(r.volume)}</td></tr>`).join('')}</tbody></table>
      </div>
      <div style="margin-top:16px"><button class="btn danger" onclick="deleteSymbol('${esc(sym)}')">删除此标的数据</button>
      <button class="btn" onclick="redownload('${esc(sym)}')">重新下载</button></div>`;
    // Render chart
    if(rows.length>0&&typeof LightweightCharts!=='undefined'){
      const chart=LightweightCharts.createChart(document.getElementById('chart'),{
        width:800,height:400,layout:{background:{color:'#0f1419'},textColor:'#e0e0e0'},
        grid:{vertLines:{color:'#1a2332'},horzLines:{color:'#1a2332'}},
        timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#2a3f5f'},
        rightPriceScale:{borderColor:'#2a3f5f'},
      });
      const candle=chart.addCandlestickSeries({upColor:'#26a69a',downColor:'#ef5350',borderUpColor:'#26a69a',borderDownColor:'#ef5350',wickUpColor:'#26a69a',wickDownColor:'#ef5350'});
      candle.setData(rows.map(r=>({time:r.ts.split('T')[0],open:r.open,high:r.high,low:r.low,close:r.close})));
      const vol=chart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'',scaleMargins:{top:0.8,bottom:0}});
      vol.setData(rows.map(r=>({time:r.ts.split('T')[0],value:r.volume,color:r.close>=r.open?'#26a69a80':'#ef535080'})));
      chart.timeScale().fitContent();
      chartInstance=chart;
      // Set range inputs from data
      document.getElementById('range-start').value=rows[0].ts.split('T')[0];
      document.getElementById('range-end').value=rows[rows.length-1].ts.split('T')[0];
    }
  }catch(e){detail.innerHTML=`<div class="msg err">Error: ${e}</div>`}
}
async function rangeIngest(sym){
  const start=document.getElementById('range-start').value;
  const end=document.getElementById('range-end').value;
  if(!confirm(`补全 ${sym} 从 ${start} 到 ${end}？`))return;
  try{const r=await api(`/ingest?symbol=${encodeURIComponent(sym)}&start=${start}&end=${end}`,{method:'POST'});
    alert(`完成: ${r.ingested} 行`);selectSymbol(sym);}
  catch(e){alert(`失败: ${e}`)}
}
function rangeExport(sym){
  const start=document.getElementById('range-start').value;
  const end=document.getElementById('range-end').value;
  window.open(`/api/v1/ohlcv?symbol=${encodeURIComponent(sym)}&start=${start}&end=${end}&format=csv`);
}
async function deleteSymbol(sym){
  if(!confirm(`确认删除 ${sym} 的全部数据？此操作不可撤销！`))return;
  try{const r=await api(`/symbols/${encodeURIComponent(sym)}`,{method:'DELETE'});
    alert(`已删除 ${r.rows_removed} 行`);currentSymbol=null;renderLocal();}
  catch(e){alert(`失败: ${e}`)}
}
async function redownload(sym){
  if(!confirm(`重新下载 ${sym}？`))return;
  try{const r=await api(`/ingest?symbol=${encodeURIComponent(sym)}`,{method:'POST'});
    alert(`完成: ${r.ingested} 行`);selectSymbol(sym);}
  catch(e){alert(`失败: ${e}`)}
}

// ── Config ─────────────────────────────────────────────────
async function renderConfig(){
  const c=document.getElementById('content');
  c.innerHTML='<div id="cfg-content">加载中...</div>';
  try{
    const[config,cache,disk]=await Promise.all([api('/config'),api('/cache'),api('/disk')]);
    document.getElementById('cfg-content').innerHTML=`
      <div class="section"><h3>数据库</h3>
        <div class="row"><label>当前路径</label><code>${esc(config.database_url)}</code></div>
        <div class="row"><label>状态</label><span class="${config.database_url?'ok':'bad'}">● ${config.database_url?'已连接':'未连接'}</span></div>
        <div class="row" style="color:#888;font-size:12px">修改路径需重启服务生效</div>
      </div>
      <div class="section"><h3>代理</h3>
        <div class="row"><label>启用</label><div class="switch ${config.proxy.enabled?'on':''}" id="proxy-switch" onclick="toggleProxy()"></div></div>
        <div class="row"><label>类型</label><select id="proxy-type"><option value="http" ${config.proxy.type==='http'?'selected':''}>HTTP</option><option value="socks5" ${config.proxy.type==='socks5'?'selected':''}>SOCKS5</option></select></div>
        <div class="row"><label>地址</label><input id="proxy-url" value="${esc(config.proxy.url)}" size="40"></div>
        <button class="btn success" onclick="saveProxy()">保存并应用（立即生效）</button>
        <div id="proxy-msg"></div>
      </div>
      <div class="section"><h3>缓存</h3>
        <div class="row"><label>类型</label>InMemoryCache</div>
        <div class="row"><label>TTL</label>${cache.ttl}秒</div>
        <div class="row"><label>当前键数</label>${cache.keys}</div>
        <button class="btn danger" onclick="clearCache()">清空缓存</button>
        <div id="cache-msg"></div>
      </div>
      <div class="section"><h3>磁盘</h3>
        <div class="row"><label>总容量</label>${disk.total_gb} GB</div>
        <div class="row"><label>已用</label>${disk.used_gb} GB (${disk.used_percent}%)</div>
        <div class="row"><label>数据库文件</label>${disk.db_file_size_mb} MB</div>
        <div class="progress-bar"><div class="progress-fill" style="width:${disk.used_percent}%"></div></div>
      </div>`;
  }catch(e){document.getElementById('cfg-content').innerHTML=`<div class="msg err">${e}</div>`}
}
function toggleProxy(){
  const sw=document.getElementById('proxy-switch');
  sw.classList.toggle('on');
}
async function saveProxy(){
  const enabled=document.getElementById('proxy-switch').classList.contains('on');
  const type=document.getElementById('proxy-type').value;
  const url=document.getElementById('proxy-url').value;
  const msg=document.getElementById('proxy-msg');
  msg.innerHTML='<div class="msg">保存中...</div>';
  try{const r=await api(`/proxy?enabled=${enabled}&proxy_type=${type}&url=${encodeURIComponent(url)}`,{method:'PUT'});
    msg.innerHTML='<div class="msg ok">已保存，立即生效</div>';}
  catch(e){msg.innerHTML=`<div class="msg err">Error: ${e}</div>`}
}
async function clearCache(){
  try{const r=await api('/cache',{method:'DELETE'});alert(`已清空 ${r.keys_removed} 个缓存键`);}
  catch(e){alert(`失败: ${e}`)}
}

// ── Logs ───────────────────────────────────────────────────
let logState={page:1,action:'',symbol:''};
async function renderLogs(){
  const c=document.getElementById('content');
  c.innerHTML=`
    <div class="row">
      <label>类型</label><select id="log-action" onchange="logState.action=this.value;logState.page=1;loadLogs()"><option value="">全部</option><option value="ingest">采集</option><option value="batch_ingest">批量采集</option><option value="delete">删除</option><option value="proxy_change">代理变更</option></select>
      <label>标的</label><input id="log-symbol" placeholder="过滤..." oninput="logState.symbol=this.value;logState.page=1;loadLogs()">
      <button class="btn" onclick="loadLogs()">刷新</button>
    </div>
    <div class="section"><table><thead><tr><th>时间</th><th>标的</th><th>操作</th><th>行数</th><th>状态</th><th>数据源</th><th>错误</th></tr></thead><tbody id="log-body"></tbody></table><div id="log-pager"></div></div>`;
  loadLogs();
}
async function loadLogs(){
  const params=`?page=${logState.page}&size=50&action=${logState.action}&symbol=${encodeURIComponent(logState.symbol)}`;
  try{
    const data=await api(`/logs${params}`);
    if(data.logs.length===0){document.getElementById('log-body').innerHTML='<tr><td colspan="7" style="text-align:center;color:#888">无记录</td></tr>';return}
    document.getElementById('log-body').innerHTML=data.logs.map(l=>`<tr>
      <td>${l.timestamp.replace('T',' ').split('.')[0]}</td><td>${esc(l.symbol)}</td><td>${l.action}</td>
      <td>${l.rows_affected||0}</td><td>${l.status==='success'?'✅':'❌'}</td><td>${l.source||'-'}</td>
      <td style="color:#ef5350;font-size:12px">${esc(l.error_message)||''}</td></tr>`).join('');
    const pager=document.getElementById('log-pager');
    if(data.total_pages>1){let h='<div class="pagination">';
      for(let i=1;i<=Math.min(data.total_pages,10);i++)h+=`<a class="${i===logState.page?'active':''}" onclick="logState.page=${i};loadLogs()">${i}</a>`;
      if(data.total_pages>10)h+=`<span>... ${data.total_pages} pages</span>`;
      h+='</div>';pager.innerHTML=h;
    }else pager.innerHTML='';
  }catch(e){document.getElementById('log-body').innerHTML=`<tr><td colspan="7" class="msg err">${e}</td></tr>`}
}

// ── Init ───────────────────────────────────────────────────
startHealthCheck();
renderDashboard();
</script>
</body>
</html>"""
