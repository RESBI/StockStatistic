"""Web admin interface plugin for StockStat storage backend.

Registers admin routes on the FastAPI app and serves a static web UI
for managing the storage server: browsing symbols, querying data,
triggering ingestion, viewing config/health, and data statistics.

Access: http://storage-server:8000/admin/
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


def create_admin_router() -> APIRouter:
    """Create the admin API router with management endpoints."""
    router = APIRouter(prefix="/admin/api", tags=["admin"])

    @router.get("/health")
    async def admin_health():
        """Detailed health check with storage and cache status."""
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

    @router.get("/config")
    async def admin_config():
        """View server configuration (read-only for safety)."""
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

    @router.get("/symbols")
    async def admin_symbols():
        """List all registered symbols with data statistics."""
        from stockstat_backend.storage.repository import ohlcv_repo, symbol_repo

        symbols = symbol_repo.list_symbols()
        result = []
        for s in symbols:
            sym = s["unified_symbol"]
            row_count = ohlcv_repo.count(symbol=sym)
            # Get date range
            df = ohlcv_repo.query(symbol=sym, limit=1)
            latest = str(df.index[0]) if not df.empty else None
            df_old = ohlcv_repo.query(symbol=sym)
            earliest = str(df_old.index[0]) if not df_old.empty else None
            result.append({
                **s,
                "row_count": row_count,
                "earliest": earliest,
                "latest": latest,
            })
        return {"count": len(result), "symbols": result}

    @router.delete("/symbols/{symbol}")
    async def admin_delete_symbol(symbol: str):
        """Delete all OHLCV data for a symbol."""
        from stockstat_backend.storage.repository import ohlcv_repo, symbol_repo
        from stockstat_backend.storage.cache import cache

        count = ohlcv_repo.count(symbol=symbol)
        # Delete OHLCV rows for this symbol
        from sqlalchemy import delete as sql_delete
        from stockstat_backend.models.ohlcv import OHLCV
        from stockstat_backend.storage.database import get_session
        with get_session() as session:
            session.execute(sql_delete(OHLCV).where(OHLCV.symbol == symbol))

        # Delete from symbol registry
        from sqlalchemy import delete as sql_del
        from stockstat_backend.models.ohlcv import SymbolRegistry
        with get_session() as session:
            session.execute(sql_del(SymbolRegistry).where(SymbolRegistry.unified_symbol == symbol))

        cache.clear()
        return {"deleted": True, "symbol": symbol, "rows_removed": count}

    @router.get("/sources")
    async def admin_sources():
        """List available data sources with status."""
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

    @router.post("/ingest")
    async def admin_ingest(symbol: str, source: Optional[str] = None,
                           start: Optional[str] = None, end: Optional[str] = None,
                           timeframe: str = "1d"):
        """Trigger data ingestion from the admin UI."""
        from stockstat_backend.api.routes import _get_adapter, _auto_detect_source
        from stockstat_backend.normalizer.normalizer import normalize_ohlcv
        from stockstat_backend.storage.repository import ohlcv_repo, symbol_repo
        from stockstat_backend.storage.cache import cache

        src = source or _auto_detect_source(symbol)
        adapter = _get_adapter(src)

        if not adapter.supports(symbol):
            raise HTTPException(400, f"Source '{src}' does not support '{symbol}'")

        try:
            df = adapter.fetch_ohlcv(symbol, start=start, end=end, timeframe=timeframe)
        except Exception as e:
            raise HTTPException(502, f"Fetch failed: {e}")

        if df.empty:
            raise HTTPException(404, f"No data for {symbol}")

        rows = normalize_ohlcv(df, symbol, src, timeframe)
        count = ohlcv_repo.upsert_many(rows)

        if "/" in symbol:
            base, quote = symbol.split("/")
            symbol_repo.upsert(symbol, "crypto", base, quote, sources=src)
        else:
            symbol_repo.upsert(symbol, "stock", symbol, sources=src)

        cache.clear()
        return {"symbol": symbol, "source": src, "ingested": count}

    @router.get("/stats")
    async def admin_stats():
        """Aggregate storage statistics."""
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

    return router


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
# Static Web UI
# ═══════════════════════════════════════════════════════════════

_ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StockStat Storage Admin</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0f1419; color: #e0e0e0; }
  .header { background: #1a2332; padding: 16px 24px; border-bottom: 2px solid #2a3f5f;
            display: flex; justify-content: space-between; align-items: center; }
  .header h1 { font-size: 20px; color: #4fc3f7; }
  .header .status { font-size: 13px; }
  .status .ok { color: #66bb6a; } .status .bad { color: #ef5350; }
  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
  .tabs { display: flex; gap: 4px; margin-bottom: 20px; }
  .tab { padding: 8px 20px; background: #1a2332; border: 1px solid #2a3f5f;
         border-radius: 6px 6px 0 0; cursor: pointer; font-size: 14px; color: #aaa; }
  .tab.active { background: #243447; color: #4fc3f7; border-bottom: 2px solid #4fc3f7; }
  .panel { display: none; background: #1a2332; border: 1px solid #2a3f5f;
           border-radius: 0 6px 6px 6px; padding: 20px; }
  .panel.active { display: block; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #2a3f5f; font-size: 13px; }
  th { color: #4fc3f7; font-weight: 600; }
  tr:hover { background: #243447; }
  .btn { padding: 6px 16px; background: #2a6496; color: #fff; border: none;
         border-radius: 4px; cursor: pointer; font-size: 13px; }
  .btn:hover { background: #3a7ab6; }
  .btn.danger { background: #c0392b; } .btn.danger:hover { background: #e74c3c; }
  .btn.success { background: #27ae60; } .btn.success:hover { background: #2ecc71; }
  input, select { padding: 6px 10px; background: #0f1419; color: #e0e0e0;
                  border: 1px solid #2a3f5f; border-radius: 4px; font-size: 13px; }
  .form-row { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
  .form-row label { min-width: 80px; font-size: 13px; color: #aaa; }
  .stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }
  .stat-card { background: #243447; padding: 16px; border-radius: 8px; text-align: center; }
  .stat-card .num { font-size: 28px; font-weight: bold; color: #4fc3f7; }
  .stat-card .label { font-size: 12px; color: #aaa; margin-top: 4px; }
  .msg { padding: 8px 16px; border-radius: 4px; margin: 8px 0; font-size: 13px; }
  .msg.ok { background: #1b3a2a; color: #66bb6a; } .msg.err { background: #3a1b1b; color: #ef5350; }
  .json { background: #0f1419; padding: 12px; border-radius: 4px; font-family: monospace;
          font-size: 12px; white-space: pre-wrap; overflow-x: auto; }
</style>
</head>
<body>
<div class="header">
  <h1>StockStat Storage Admin</h1>
  <div class="status" id="hdr-status">Checking...</div>
</div>
<div class="container">
  <div class="tabs">
    <div class="tab active" onclick="showTab('overview')">Overview</div>
    <div class="tab" onclick="showTab('symbols')">Symbols</div>
    <div class="tab" onclick="showTab('ingest')">Ingest</div>
    <div class="tab" onclick="showTab('config')">Config</div>
    <div class="tab" onclick="showTab('sources')">Sources</div>
  </div>

  <div class="panel active" id="p-overview">
    <div class="stats" id="stats"></div>
    <h3 style="margin-top:24px;color:#4fc3f7">Health</h3>
    <div id="health" class="json">Loading...</div>
  </div>

  <div class="panel" id="p-symbols">
    <table id="sym-table"><thead><tr>
      <th>Symbol</th><th>Type</th><th>Base</th><th>Quote</th><th>Sources</th>
      <th>Rows</th><th>Earliest</th><th>Latest</th><th></th>
    </tr></thead><tbody id="sym-body"></tbody></table>
  </div>

  <div class="panel" id="p-ingest">
    <div class="form-row"><label>Symbol</label><input id="ing-sym" value="BTC/USDT" size="20"></div>
    <div class="form-row"><label>Source</label><input id="ing-src" placeholder="auto" size="15"></div>
    <div class="form-row"><label>Start</label><input id="ing-start" placeholder="2024-01-01" size="15"></div>
    <div class="form-row"><label>End</label><input id="ing-end" placeholder="2024-12-31" size="15"></div>
    <div class="form-row"><label>Timeframe</label><select id="ing-tf">
      <option>1d</option><option>1h</option><option>4h</option><option>1m</option><option>1w</option>
    </select></div>
    <button class="btn success" onclick="doIngest()">Ingest</button>
    <div id="ing-msg"></div>
  </div>

  <div class="panel" id="p-config">
    <div id="config-data" class="json">Loading...</div>
  </div>

  <div class="panel" id="p-sources">
    <table><thead><tr><th>Name</th><th>Type</th><th>Description</th></tr></thead>
    <tbody id="src-body"></tbody></table>
  </div>
</div>

<script>
const API = '/admin/api';
function showTab(id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('p-'+id).classList.add('active');
  if (id==='overview') loadOverview();
  if (id==='symbols') loadSymbols();
  if (id==='config') loadConfig();
  if (id==='sources') loadSources();
}
async function api(path, opts) {
  const r = await fetch(API+path, opts);
  if (!r.ok) { const e = await r.json().catch(()=>({detail:r.statusText})); throw new Error(e.detail||r.status); }
  return r.json();
}
async function loadOverview() {
  try {
    const [stats, health] = await Promise.all([api('/stats'), api('/health')]);
    document.getElementById('stats').innerHTML = `
      <div class="stat-card"><div class="num">${stats.total_symbols}</div><div class="label">Symbols</div></div>
      <div class="stat-card"><div class="num">${stats.total_rows.toLocaleString()}</div><div class="label">Total Rows</div></div>
      <div class="stat-card"><div class="num">${Object.entries(stats.symbols_by_source||{}).map(([k,v])=>k+': '+v).join(', ')||'-'}</div><div class="label">By Source</div></div>`;
    const h = health.database;
    document.getElementById('hdr-status').innerHTML =
      `<span class="${health.status==='ok'?'ok':'bad'}">● ${health.status.toUpperCase()}</span> DB: ${h.url}`;
    document.getElementById('health').textContent = JSON.stringify(health, null, 2);
  } catch(e) { document.getElementById('health').textContent = 'Error: '+e; }
}
async function loadSymbols() {
  try {
    const data = await api('/symbols');
    document.getElementById('sym-body').innerHTML = data.symbols.map(s => `
      <tr><td>${s.unified_symbol}</td><td>${s.asset_type}</td><td>${s.base_asset||''}</td>
      <td>${s.quote_asset||''}</td><td>${(s.sources||[]).join(', ')}</td>
      <td>${(s.row_count||0).toLocaleString()}</td><td>${s.earliest||'-'}</td><td>${s.latest||'-'}</td>
      <td><button class="btn danger" onclick="delSym('${s.unified_symbol}')">Delete</button></td></tr>`).join('');
  } catch(e) { alert('Error: '+e); }
}
async function delSym(sym) {
  if (!confirm('Delete all data for '+sym+'?')) return;
  try { await api('/symbols/'+encodeURIComponent(sym), {method:'DELETE'}); loadSymbols(); }
  catch(e) { alert('Error: '+e); }
}
async function doIngest() {
  const p = new URLSearchParams();
  const sym=document.getElementById('ing-sym').value; p.set('symbol',sym);
  const src=document.getElementById('ing-src').value; if(src)p.set('source',src);
  const st=document.getElementById('ing-start').value; if(st)p.set('start',st);
  const en=document.getElementById('ing-end').value; if(en)p.set('end',en);
  const tf=document.getElementById('ing-tf').value; p.set('timeframe',tf);
  document.getElementById('ing-msg').innerHTML='<div class="msg">Ingesting...</div>';
  try { const r=await api('/ingest?'+p, {method:'POST'});
    document.getElementById('ing-msg').innerHTML=`<div class="msg ok">Done: ${r.ingested} rows ingested</div>`; }
  catch(e) { document.getElementById('ing-msg').innerHTML=`<div class="msg err">Error: ${e}</div>`; }
}
async function loadConfig() {
  try { const c=await api('/config'); document.getElementById('config-data').textContent=JSON.stringify(c,null,2); }
  catch(e) { document.getElementById('config-data').textContent='Error: '+e; }
}
async function loadSources() {
  try { const d=await api('/sources');
    document.getElementById('src-body').innerHTML=d.sources.map(s=>`<tr><td>${s.name}</td><td>${s.type}</td><td>${s.description}</td></tr>`).join(''); }
  catch(e) { alert('Error: '+e); }
}
loadOverview();
</script>
</body>
</html>"""


def mount_admin(app) -> None:
    """Mount the admin router and static UI on a FastAPI app.

    Call this during app startup to enable the admin interface at
    ``/admin/``.
    """
    router = create_admin_router()
    app.include_router(router)

    @app.get("/admin", response_class=HTMLResponse)
    @app.get("/admin/", response_class=HTMLResponse)
    async def admin_ui():
        return HTMLResponse(content=_ADMIN_HTML)
