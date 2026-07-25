#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════
#  V3 Deployment Case C — Offline mode (no backend)
#
#  Scenario: V2Client(mode="offline") with local Storage
#  (Memory / SQL). No HTTP backend process. Compute via
#  default LocalComputeBackend. Tests V3 compute.remote()
#  / cluster_info() in offline mode.
#
#  Usage:
#    ./run_case_c_offline.sh
#    ./run_case_c_offline.sh --verbose
# ════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# -- V3 environment --
export STOCKSTAT_TRANSPORT="in_process"
export STOCKSTAT_DISPATCHER_ENABLED="false"
export STOCKSTAT_DISPATCHER_URL=""
export STOCKSTAT_SKIP_NETWORK="true"
export STOCKSTAT_TEST_SYMBOL="BTC/USDT"

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
"$PYTHON_CMD" test_case_c_offline.py "$@"
