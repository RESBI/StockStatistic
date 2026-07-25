@echo off
setlocal EnableDelayedExpansion
:: ==================================================
::  V3 Deployment Case F — Multi-level Dispatcher
::
::  Scenario: Parent Dispatcher with sub-Dispatcher(s)
::  registered. Validates P7 multi-level topology +
::  Admin monitoring endpoints.
::
::  Usage:
::    run_case_f_multilevel.bat
::    run_case_f_multilevel.bat --verbose
:: ==================================================

set "SCRIPT_DIR=%~dp0"

:: -- V3 environment --
set "STOCKSTAT_TRANSPORT=http"
set "STOCKSTAT_DISPATCHER_ENABLED=true"
set "STOCKSTAT_ADMIN_ENABLED=true"
set "STOCKSTAT_SKIP_NETWORK=true"

:: -- Locate Python --
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    exit /b 1
)

cd /d "%SCRIPT_DIR%"
python test_case_f_multilevel.py %*
exit /b %ERRORLEVEL%
