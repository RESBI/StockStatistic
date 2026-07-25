@echo off
setlocal EnableDelayedExpansion
:: ==================================================
::  V3 Deployment Case A — Single-machine full-stack
::
::  Scenario: Storage + Client + Compute all in-process
::  No backend process needed. Tests both v2.1 direct
::  calls and V3 remote() / cluster_info() entry points.
::
::  Usage:
::    run_case_a_single_machine.bat             Default run
::    run_case_a_single_machine.bat --verbose   Verbose output
:: ==================================================

:: -- Resolve script directory (tests/deployments/) --
set "SCRIPT_DIR=%~dp0"

:: -- V3 environment configuration --
:: Scenario A: no HTTP backend; in-process transport
set "STOCKSTAT_TRANSPORT=in_process"
set "STOCKSTAT_DISPATCHER_ENABLED=false"
set "STOCKSTAT_DISPATCHER_URL="
:: Optional: skip any network-touching steps
set "STOCKSTAT_SKIP_NETWORK=true"
:: Test data range
set "STOCKSTAT_TEST_SYMBOL=BTC/USDT"
set "STOCKSTAT_TEST_START=2024-01-01"
set "STOCKSTAT_TEST_END=2024-12-31"

:: -- Locate Python --
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo         Install Python 3.10+ and retry.
    exit /b 1
)

:: -- Run the test script --
cd /d "%SCRIPT_DIR%"
python test_case_a_single_machine.py %*

:: -- Propagate exit code --
exit /b %ERRORLEVEL%
