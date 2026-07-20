@echo off
setlocal EnableDelayedExpansion
:: ==================================================
::  V3 Deployment Case D — Explicit LocalComputeBackend
::
::  Scenario: Explicitly inject LocalComputeBackend into
::  StockStatClient / V2Client. Exercises the full V3
::  API surface (remote / cluster_info / TaskRef lifecycle
::  / cancel / stream_results / all task types).
::
::  Usage:
::    run_case_d_local_compute_backend.bat
::    run_case_d_local_compute_backend.bat --verbose
:: ==================================================

set "SCRIPT_DIR=%~dp0"

:: -- V3 environment --
set "STOCKSTAT_TRANSPORT=in_process"
set "STOCKSTAT_DISPATCHER_ENABLED=false"
set "STOCKSTAT_SKIP_NETWORK=true"

:: -- Locate Python --
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    exit /b 1
)

cd /d "%SCRIPT_DIR%"
python test_case_d_local_compute_backend.py %*
exit /b %ERRORLEVEL%
