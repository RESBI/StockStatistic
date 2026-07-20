#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════
#  V3 Deployment Case B — Storage-compute separation
#
#  Scenario: Backend (stockstat_backend) runs as a separate
#  process. Client connects via HTTP for data access; compute
#  happens locally via LocalComputeBackend.
#
#  This launcher:
#    1. Checks backend is reachable; starts one if not
#    2. Sets V3 environment variables
#    3. Runs test_case_b_storage_separated.py
#
#  Usage:
#    ./run_case_b_storage_separated.sh                       # localhost:8000
#    ./run_case_b_storage_separated.sh --host 192.168.1.100  # remote backend
#    ./run_case_b_storage_separated.sh --skip-start          # don't auto-start
# ════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# -- Configuration (overridable via env or args) --
export STOCKSTAT_HOST="${STOCKSTAT_HOST:-localhost}"
export STOCKSTAT_PORT="${STOCKSTAT_PORT:-8000}"
SKIP_START=0
VERBOSE=""

# -- Parse args --
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            export STOCKSTAT_HOST="$2"
            shift 2
            ;;
        --port)
            export STOCKSTAT_PORT="$2"
            shift 2
            ;;
        --skip-start)
            SKIP_START=1
            shift
            ;;
        --verbose)
            VERBOSE="--verbose"
            shift
            ;;
        *)
            echo "[WARN] Unknown option: $1"
            shift
            ;;
    esac
done

# -- V3 environment --
export STOCKSTAT_TRANSPORT="in_process"
export STOCKSTAT_DISPATCHER_ENABLED="false"
export STOCKSTAT_DISPATCHER_URL=""
export STOCKSTAT_TEST_SYMBOL="BTC/USDT"
export STOCKSTAT_TEST_START="2024-01-01"
export STOCKSTAT_TEST_END="2024-12-31"

# -- Locate Python --
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python not found in PATH."
    exit 1
fi

# -- Optionally auto-start backend --
BACKEND_PID=""
if [[ "$SKIP_START" == "0" && "$STOCKSTAT_HOST" == "localhost" ]]; then
    echo "[INFO] Checking backend at http://$STOCKSTAT_HOST:$STOCKSTAT_PORT ..."
    if ! "$PYTHON_CMD" -c "import httpx; r=httpx.get('http://$STOCKSTAT_HOST:$STOCKSTAT_PORT/api/v1/health', timeout=2); exit(0 if r.status_code==200 else 1)" &>/dev/null; then
        echo "[INFO] Backend not running. Starting one in background ..."
        export DATABASE_URL="sqlite:///$PROJECT_ROOT/stockstat.db"
        export STOCKSTAT_ADMIN_ENABLED="false"
        cd "$PROJECT_ROOT/backend"
        "$PYTHON_CMD" -m uvicorn stockstat_backend.app:app \
            --host 127.0.0.1 --port "$STOCKSTAT_PORT" \
            > "$PROJECT_ROOT/backend_test.log" 2>&1 &
        BACKEND_PID=$!
        cd "$SCRIPT_DIR"
        # Wait up to 15s for backend to be ready
        for i in {1..15}; do
            sleep 1
            if "$PYTHON_CMD" -c "import httpx; r=httpx.get('http://$STOCKSTAT_HOST:$STOCKSTAT_PORT/api/v1/health', timeout=1); exit(0 if r.status_code==200 else 1)" &>/dev/null; then
                echo "[INFO] Backend ready after ${i}s (pid=$BACKEND_PID)"
                break
            fi
            if [[ "$i" == "15" ]]; then
                echo "[ERROR] Backend failed to start within 15s. See backend_test.log"
                exit 1
            fi
        done
    else
        echo "[INFO] Backend already running."
    fi
fi

# -- Run the test --
cd "$SCRIPT_DIR"
set +e
"$PYTHON_CMD" test_case_b_storage_separated.py \
    --host "$STOCKSTAT_HOST" --port "$STOCKSTAT_PORT" $VERBOSE
EXIT_CODE=$?
set -e

# -- Cleanup --
if [[ -n "$BACKEND_PID" ]]; then
    echo "[INFO] Stopping backend (pid=$BACKEND_PID) ..."
    kill "$BACKEND_PID" 2>/dev/null || true
fi

exit $EXIT_CODE
