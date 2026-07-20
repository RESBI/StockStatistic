@echo off
:: StockStat Backend - Quick Start
set "HOST=0.0.0.0"                              :: Listen address
set "PORT=8000"                                 :: Listen port
set "DATABASE_URL=sqlite:///stockstat.db"       :: SQLite file (use sqlite:////abs/path for absolute, postgresql://... for production)
set "REDIS_URL="                                :: Redis connection (optional, leave empty to skip)
set "STOCKSTAT_DEFAULT_SOURCE=yfinance"         :: Default data source when auto-detect fails
set "STOCKSTAT_PROXY_ENABLED=false"             :: Enable proxy (true/false)
set "STOCKSTAT_PROXY_TYPE=http"                 :: Proxy type (http/socks5)
set "STOCKSTAT_PROXY_URL=http://127.0.0.1:8889" :: Proxy URL
set "STOCKSTAT_ADMIN_ENABLED=true"              :: Web admin UI at /admin/ (true/false)
python -m uvicorn stockstat_backend.app:app --host %HOST% --port %PORT%
