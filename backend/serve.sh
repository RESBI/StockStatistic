#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════
#  StockStat Backend Service — Linux/macOS Startup Script
#  Usage:
#    ./serve.sh                        Start with defaults
#    ./serve.sh --config               Interactive configuration
#    ./serve.sh --host 0.0.0.0 --port 9000   Override params
# ════════════════════════════════════════════════════════════

set -euo pipefail

# ── Resolve project root (parent of backend/) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Defaults ──
SS_HOST="0.0.0.0"
SS_PORT="8000"
SS_DB_URL=""
SS_REDIS_URL=""
SS_PROXY_ENABLED="false"
SS_PROXY_TYPE="http"
SS_PROXY_URL="http://127.0.0.1:8889"
SS_ADMIN_ENABLED="true"
SS_DEFAULT_SOURCE="yfinance"
SS_RELOAD=0
INTERACTIVE=0

# ── Color output (if terminal supports it) ──
if [ -t 1 ]; then
    BOLD='\033[1m'
    CYAN='\033[0;36m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    RED='\033[0;31m'
    NC='\033[0m' # No Color
else
    BOLD=''
    CYAN=''
    GREEN=''
    YELLOW=''
    RED=''
    NC=''
fi

# ── Parse command-line args ──
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            INTERACTIVE=1
            shift
            ;;
        --host)
            SS_HOST="$2"
            shift 2
            ;;
        --port)
            SS_PORT="$2"
            shift 2
            ;;
        --db-url)
            SS_DB_URL="$2"
            shift 2
            ;;
        --redis-url)
            SS_REDIS_URL="$2"
            shift 2
            ;;
        --proxy)
            SS_PROXY_ENABLED="true"
            SS_PROXY_TYPE="$2"
            SS_PROXY_URL="$3"
            shift 3
            ;;
        --no-admin)
            SS_ADMIN_ENABLED="false"
            shift
            ;;
        --reload)
            SS_RELOAD=1
            shift
            ;;
        --help|-h)
            show_help=1
            break
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help=1
            break
            ;;
    esac
done

if [[ "${show_help:-0}" == "1" ]]; then
    echo ""
    echo "StockStat Backend Service Startup Script"
    echo ""
    echo "Usage:"
    echo "  ./serve.sh                              Start with defaults"
    echo "  ./serve.sh --config                     Interactive configuration"
    echo "  ./serve.sh --host 0.0.0.0 --port 9000   Override host and port"
    echo "  ./serve.sh --db-url 'sqlite:////data/stockstat.db'"
    echo "  ./serve.sh --redis-url 'redis://localhost:6379/0'"
    echo "  ./serve.sh --proxy http http://127.0.0.1:8889"
    echo "  ./serve.sh --no-admin                   Disable web admin UI"
    echo "  ./serve.sh --reload                     Enable hot reload (dev mode)"
    echo "  ./serve.sh --help                       Show this help"
    echo ""
    echo "Options can be combined:"
    echo "  ./serve.sh --config --reload"
    echo "  ./serve.sh --host 0.0.0.0 --port 9000 --proxy socks5 socks5://127.0.0.1:1089"
    echo ""
    exit 0
fi

# ── Interactive configuration ──
if [[ "$INTERACTIVE" == "1" ]]; then
    echo ""
    echo -e "${CYAN}═══ StockStat Backend Configuration ═══${NC}"
    echo ""

    # Host
    read -rp "Listen host [0.0.0.0]: " INPUT_HOST
    SS_HOST="${INPUT_HOST:-$SS_HOST}"

    # Port
    read -rp "Listen port [8000]: " INPUT_PORT
    SS_PORT="${INPUT_PORT:-$SS_PORT}"

    # Database
    echo ""
    echo "Database options:"
    echo "  1. SQLite (default, file-based)"
    echo "  2. PostgreSQL / TimescaleDB"
    echo "  3. Custom DATABASE_URL"
    read -rp "Choose [1]: " DB_CHOICE
    DB_CHOICE="${DB_CHOICE:-1}"
    case "$DB_CHOICE" in
        2)
            read -rp "PostgreSQL host [localhost]: " PG_HOST
            PG_HOST="${PG_HOST:-localhost}"
            read -rp "PostgreSQL port [5432]: " PG_PORT
            PG_PORT="${PG_PORT:-5432}"
            read -rp "Database name [stockstat]: " PG_DB
            PG_DB="${PG_DB:-stockstat}"
            read -rp "Username [stockstat]: " PG_USER
            PG_USER="${PG_USER:-stockstat}"
            read -rsp "Password: " PG_PASS
            echo ""
            SS_DB_URL="postgresql://${PG_USER}:${PG_PASS}@${PG_HOST}:${PG_PORT}/${PG_DB}"
            ;;
        3)
            read -rp "DATABASE_URL: " SS_DB_URL
            ;;
        *)
            read -rp "SQLite file path [stockstat.db]: " SQLITE_PATH
            SQLITE_PATH="${SQLITE_PATH:-stockstat.db}"
            # Check if absolute path
            if [[ "$SQLITE_PATH" == /* ]]; then
                SS_DB_URL="sqlite://${SQLITE_PATH}"
            else
                SS_DB_URL="sqlite:///${SQLITE_PATH}"
            fi
            ;;
    esac

    # Proxy
    echo ""
    read -rp "Enable proxy? [y/N]: " INPUT_PROXY
    if [[ "${INPUT_PROXY,,}" == "y" ]]; then
        SS_PROXY_ENABLED="true"
        read -rp "Proxy type [http]: " INPUT_PROXY_TYPE
        SS_PROXY_TYPE="${INPUT_PROXY_TYPE:-http}"
        if [[ "$SS_PROXY_TYPE" == "http" ]]; then
            SS_PROXY_URL="http://127.0.0.1:8889"
        else
            SS_PROXY_URL="socks5://127.0.0.1:1089"
        fi
        read -rp "Proxy URL [$SS_PROXY_URL]: " INPUT_PROXY_URL
        SS_PROXY_URL="${INPUT_PROXY_URL:-$SS_PROXY_URL}"
    fi

    # Admin
    echo ""
    read -rp "Enable web admin? [Y/n]: " INPUT_ADMIN
    if [[ "${INPUT_ADMIN,,}" == "n" ]]; then
        SS_ADMIN_ENABLED="false"
    fi

    # Reload
    echo ""
    read -rp "Enable hot reload (dev mode)? [y/N]: " INPUT_RELOAD
    if [[ "${INPUT_RELOAD,,}" == "y" ]]; then
        SS_RELOAD=1
    fi

    # Summary
    echo ""
    echo -e "${CYAN}═══ Configuration Summary ═══${NC}"
    echo "  Host:         $SS_HOST"
    echo "  Port:         $SS_PORT"
    if [[ -n "$SS_DB_URL" ]]; then
        echo "  Database:     $SS_DB_URL"
    else
        echo "  Database:     sqlite:///stockstat.db (default)"
    fi
    if [[ -n "$SS_REDIS_URL" ]]; then
        echo "  Redis:        $SS_REDIS_URL"
    fi
    echo "  Proxy:        $SS_PROXY_ENABLED"
    if [[ "$SS_PROXY_ENABLED" == "true" ]]; then
        echo "  Proxy URL:    $SS_PROXY_URL"
    fi
    echo "  Admin UI:     $SS_ADMIN_ENABLED"
    echo "  Reload:       $SS_RELOAD"
    echo ""
    read -rp "Start server? [Y/n]: " CONFIRM
    if [[ "${CONFIRM,,}" == "n" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# ── Set environment variables ──
export HOST="$SS_HOST"
export PORT="$SS_PORT"
if [[ -n "$SS_DB_URL" ]]; then
    export DATABASE_URL="$SS_DB_URL"
fi
if [[ -n "$SS_REDIS_URL" ]]; then
    export REDIS_URL="$SS_REDIS_URL"
fi
export STOCKSTAT_PROXY_ENABLED="$SS_PROXY_ENABLED"
export STOCKSTAT_PROXY_TYPE="$SS_PROXY_TYPE"
export STOCKSTAT_PROXY_URL="$SS_PROXY_URL"
export STOCKSTAT_ADMIN_ENABLED="$SS_ADMIN_ENABLED"
export STOCKSTAT_DEFAULT_SOURCE="$SS_DEFAULT_SOURCE"

# ── Check Python availability ──
if ! command -v python3 &>/dev/null; then
    if ! command -v python &>/dev/null; then
        echo -e "${RED}[ERROR] Python not found in PATH. Please install Python 3.10+.${NC}"
        exit 1
    fi
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

# ── Check backend package ──
if ! "$PYTHON_CMD" -c "import stockstat_backend" &>/dev/null; then
    echo -e "${RED}[ERROR] stockstat_backend not installed.${NC}"
    echo "       Run: cd backend && pip install -e ."
    exit 1
fi

# ── Determine display host (use localhost for 0.0.0.0) ──
DISPLAY_HOST="$SS_HOST"
if [[ "$SS_HOST" == "0.0.0.0" ]]; then
    DISPLAY_HOST="localhost"
fi

# ── Start server ──
echo ""
echo -e "${GREEN}═══ Starting StockStat Backend ═══${NC}"
echo "  Host:     $SS_HOST"
echo "  Port:     $SS_PORT"
echo "  Database: ${DATABASE_URL:-sqlite:///stockstat.db}"
echo -e "  Admin:    ${CYAN}http://${DISPLAY_HOST}:${SS_PORT}/admin/${NC}"
echo -e "  API:      ${CYAN}http://${DISPLAY_HOST}:${SS_PORT}/api/v1/health${NC}"
echo ""

if [[ "$SS_RELOAD" == "1" ]]; then
    exec "$PYTHON_CMD" -m uvicorn stockstat_backend.app:app --host "$SS_HOST" --port "$SS_PORT" --reload
else
    exec "$PYTHON_CMD" -m uvicorn stockstat_backend.app:app --host "$SS_HOST" --port "$SS_PORT"
fi
