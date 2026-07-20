@echo off
setlocal EnableDelayedExpansion
:: ==================================================
::  V3 Deployment Case B — Storage-compute separation
::
::  Scenario: Backend (stockstat_backend) runs as a
::  separate process. Client connects via HTTP for data
::  access; compute happens locally via LocalComputeBackend.
::
::  This launcher:
::    1. Checks backend is reachable; starts one if not
::    2. Sets V3 environment variables
::    3. Runs test_case_b_storage_separated.py
::
::  Usage:
::    run_case_b_storage_separated.bat                       # localhost:8000
::    run_case_b_storage_separated.bat --host 192.168.1.100  # remote backend
::    run_case_b_storage_separated.bat --skip-start          # don't auto-start
:: ==================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."

:: -- Configuration (overridable via env or args) --
if not defined STOCKSTAT_HOST set "STOCKSTAT_HOST=localhost"
if not defined STOCKSTAT_PORT set "STOCKSTAT_PORT=8000"
set "SKIP_START=0"

:: -- Parse args --
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--host" (
    set "STOCKSTAT_HOST=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--port" (
    set "STOCKSTAT_PORT=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--skip-start" (
    set "SKIP_START=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--verbose" (
    set "VERBOSE=--verbose"
    shift
    goto :parse_args
)
shift
goto :parse_args
:args_done

:: -- V3 environment --
set "STOCKSTAT_TRANSPORT=in_process"
set "STOCKSTAT_DISPATCHER_ENABLED=false"
set "STOCKSTAT_DISPATCHER_URL="
set "STOCKSTAT_TEST_SYMBOL=BTC/USDT"
set "STOCKSTAT_TEST_START=2024-01-01"
set "STOCKSTAT_TEST_END=2024-12-31"

:: -- Locate Python --
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    exit /b 1
)

:: -- Optionally auto-start backend --
if "%SKIP_START%"=="0" if "%STOCKSTAT_HOST%"=="localhost" (
    echo [INFO] Checking backend at http://%STOCKSTAT_HOST%:%STOCKSTAT_PORT% ...
    python -c "import httpx; r=httpx.get('http://%STOCKSTAT_HOST%:%STOCKSTAT_PORT%/api/v1/health', timeout=2); exit(0 if r.status_code==200 else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [INFO] Backend not running. Starting one in background ...
        if not exist "%PROJECT_ROOT%\stockstat.db" (
            echo [INFO] Using SQLite at %PROJECT_ROOT%\stockstat.db
        )
        set "DATABASE_URL=sqlite:////%PROJECT_ROOT%\stockstat.db"
        set "STOCKSTAT_ADMIN_ENABLED=false"
        start "stockstat-backend" /min cmd /c "cd /d %PROJECT_ROOT%\backend && python -m uvicorn stockstat_backend.app:app --host 127.0.0.1 --port %STOCKSTAT_PORT% > backend_test.log 2>&1"
        :: Wait up to 15s for backend to be ready
        for /l %%i in (1,1,15) do (
            timeout /t 1 /nobreak >nul
            python -c "import httpx; r=httpx.get('http://%STOCKSTAT_HOST%:%STOCKSTAT_PORT%/api/v1/health', timeout=1); exit(0 if r.status_code==200 else 1)" >nul 2>&1
            if not errorlevel 1 (
                echo [INFO] Backend ready after %%i s
                goto :backend_ready
            )
        )
        echo [ERROR] Backend failed to start within 15s. See backend_test.log
        exit /b 1
        :backend_ready
    ) else (
        echo [INFO] Backend already running.
    )
)

:: -- Run the test --
cd /d "%SCRIPT_DIR%"
python test_case_b_storage_separated.py --host %STOCKSTAT_HOST% --port %STOCKSTAT_PORT% %VERBOSE%
set "EXIT_CODE=%ERRORLEVEL%"

:: -- Cleanup: don't kill the backend we started (may be used by other tests) --
exit /b %EXIT_CODE%
