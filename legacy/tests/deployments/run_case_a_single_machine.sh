#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════
#  V3 Deployment Case A — Single-machine full-stack
#
#  Scenario: Storage + Client + Compute all in-process
#  No backend process needed. Tests both v2.1 direct calls
#  and V3 remote() / cluster_info() entry points.
#
#  Usage:
#    ./run_case_a_single_machine.sh             Default run
#    ./run_case_a_single_machine.sh --verbose   Verbose output
# ════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# -- V3 environment configuration --
# Scenario A: no HTTP backend; in-process transport
export STOCKSTAT_TRANSPORT="in_process"
export STOCKSTAT_DISPATCHER_ENABLED="false"
export STOCKSTAT_DISPATCHER_URL=""
# Optional: skip any network-touching steps
export STOCKSTAT_SKIP_NETWORK="true"
# Test data range
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
    echo "        Install Python 3.10+ and retry."
    exit 1
fi

# -- Run the test script --
cd "$SCRIPT_DIR"
"$PYTHON_CMD" test_case_a_single_machine.py "$@"
