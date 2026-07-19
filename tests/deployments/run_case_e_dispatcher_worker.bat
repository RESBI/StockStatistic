@echo off
setlocal EnableDelayedExpansion
:: ==================================================
::  V3 Deployment Case E — Dispatcher + Worker
::
::  Scenario: Storage + Dispatcher (FastAPI) + Worker
::  (background thread) + Client (RemoteComputeBackend).
::
::  Validates the full V3 distributed compute path with
::  httpx bridged to FastAPI TestClient (no real network).
::
::  Usage:
::    run_case_e_dispatcher_worker.bat
::    run_case_e_dispatcher_worker.bat --verbose
:: ==================================================

set "SCRIPT_DIR=%~dp0"

:: -- V3 environment --
set "STOCKSTAT_TRANSPORT=http"
set "STOCKSTAT_DISPATCHER_ENABLED=true"
set "STOCKSTAT_SKIP_NETWORK=true"

:: -- Locate Python --
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    exit /b 1
)

cd /d "%SCRIPT_DIR%"
python test_case_e_dispatcher_worker.py %*
exit /b %ERRORLEVEL%
