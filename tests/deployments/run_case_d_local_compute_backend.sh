#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════
#  V3 Deployment Case D — Explicit LocalComputeBackend
#
#  Scenario: Explicitly inject LocalComputeBackend into
#  StockStatClient / V2Client. Exercises the full V3 API
#  surface (remote / cluster_info / TaskRef lifecycle /
#  cancel / stream_results / all task types).
#
#  Usage:
#    ./run_case_d_local_compute_backend.sh
#    ./run_case_d_local_compute_backend.sh --verbose
# ════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# -- V3 environment --
export STOCKSTAT_TRANSPORT="in_process"
export STOCKSTAT_DISPATCHER_ENABLED="false"
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
"$PYTHON_CMD" test_case_d_local_compute_backend.py "$@"
