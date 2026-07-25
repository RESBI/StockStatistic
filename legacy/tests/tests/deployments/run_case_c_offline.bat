@echo off
setlocal EnableDelayedExpansion
:: ==================================================
::  V3 Deployment Case C — Offline mode (no backend)
::
::  Scenario: V2Client(mode="offline") with local
::  Storage (Memory / SQL). No HTTP backend process.
::  Compute via default LocalComputeBackend. Tests V3
::  compute.remote() / cluster_info() in offline mode.
::
::  Usage:
::    run_case_c_offline.bat
::    run_case_c_offline.bat --verbose
:: ==================================================

set "SCRIPT_DIR=%~dp0"

:: -- V3 environment --
set "STOCKSTAT_TRANSPORT=in_process"
set "STOCKSTAT_DISPATCHER_ENABLED=false"
set "STOCKSTAT_DISPATCHER_URL="
set "STOCKSTAT_SKIP_NETWORK=true"
set "STOCKSTAT_TEST_SYMBOL=BTC/USDT"

:: -- Locate Python --
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    exit /b 1
)

cd /d "%SCRIPT_DIR%"
python test_case_c_offline.py %*
exit /b %ERRORLEVEL%
