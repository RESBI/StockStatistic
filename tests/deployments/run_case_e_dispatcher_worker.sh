#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════
#  V3 Deployment Case E — Dispatcher + Worker
#
#  Scenario: Storage + Dispatcher (FastAPI) + Worker
#  (background thread) + Client (RemoteComputeBackend).
#
#  Validates the full V3 distributed compute path with
#  httpx bridged to FastAPI TestClient (no real network).
#
#  Usage:
#    ./run_case_e_dispatcher_worker.sh
#    ./run_case_e_dispatcher_worker.sh --verbose
# ════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# -- V3 environment --
export STOCKSTAT_TRANSPORT="http"
export STOCKSTAT_DISPATCHER_ENABLED="true"
export STOCKSTAT_SKIP_NETWORK="true"

# -- Locate Python --
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python not found in PATH."
    exit 1
fi

cd "$SCRIPT_DIR"
"$PYTHON_CMD" test_case_e_dispatcher_worker.py "$@"
