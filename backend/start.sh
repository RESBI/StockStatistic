#!/usr/bin/env bash
# StockStat Backend - Quick Start
export HOST="0.0.0.0"                              # Listen address
export PORT="8000"                                 # Listen port
export DATABASE_URL="sqlite:///stockstat.db"       # SQLite file (use sqlite:////abs/path for absolute, postgresql://... for production)
export REDIS_URL=""                                # Redis connection (optional, leave empty to skip)
export STOCKSTAT_DEFAULT_SOURCE="yfinance"         # Default data source when auto-detect fails
export STOCKSTAT_PROXY_ENABLED="false"             # Enable proxy (true/false)
export STOCKSTAT_PROXY_TYPE="http"                 # Proxy type (http/socks5)
export STOCKSTAT_PROXY_URL="http://127.0.0.1:8889" # Proxy URL
export STOCKSTAT_ADMIN_ENABLED="true"              # Web admin UI at /admin/ (true/false)
python3 -m uvicorn stockstat_backend.app:app --host "$HOST" --port "$PORT"
