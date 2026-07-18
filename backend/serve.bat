@echo off
setlocal EnableDelayedExpansion

:: ==================================================
::  StockStat Backend Service - Windows Startup Script
::
::  Usage:
::    serve.bat                      Start with defaults
::    serve.bat --config             Interactive configuration
::    serve.bat --host 0.0.0.0 --port 9000   Override params
:: ==================================================

:: -- Defaults --
set "SS_HOST=0.0.0.0"
set "SS_PORT=8000"
set "SS_DB_URL="
set "SS_REDIS_URL="
set "SS_PROXY_ENABLED=false"
set "SS_PROXY_TYPE=http"
set "SS_PROXY_URL=http://127.0.0.1:8889"
set "SS_ADMIN_ENABLED=true"
set "SS_DEFAULT_SOURCE=yfinance"
set "SS_RELOAD=0"
set "INTERACTIVE=0"

:: -- Parse command-line args --
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--config" (
    set "INTERACTIVE=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--host" (
    set "SS_HOST=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--port" (
    set "SS_PORT=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--db-url" (
    set "SS_DB_URL=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--redis-url" (
    set "SS_REDIS_URL=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--proxy" (
    set "SS_PROXY_ENABLED=true"
    set "SS_PROXY_TYPE=%~2"
    set "SS_PROXY_URL=%~3"
    shift
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--no-admin" (
    set "SS_ADMIN_ENABLED=false"
    shift
    goto :parse_args
)
if /i "%~1"=="--reload" (
    set "SS_RELOAD=1"
    shift
    goto :parse_args
)
if /i "%~1"=="--help" goto :show_help
echo Unknown option: %~1
goto :show_help
:args_done

:: -- Skip interactive config if not requested --
if not "!INTERACTIVE!"=="1" goto :start_server

:: -- Interactive configuration --
echo.
echo === StockStat Backend Configuration ===
echo.

set /p "INPUT_HOST=Listen host [0.0.0.0]: "
if not "!INPUT_HOST!"=="" set "SS_HOST=!INPUT_HOST!"

set /p "INPUT_PORT=Listen port [8000]: "
if not "!INPUT_PORT!"=="" set "SS_PORT=!INPUT_PORT!"

echo.
echo Database options:
echo   1. SQLite (default, file-based)
echo   2. PostgreSQL / TimescaleDB
echo   3. Custom DATABASE_URL
set /p "DB_CHOICE=Choose [1]: "
if "!DB_CHOICE!"=="2" goto :config_pg
if "!DB_CHOICE!"=="3" goto :config_custom_db
:: Default: SQLite
set /p "SQLITE_PATH=SQLite file path [stockstat.db]: "
if "!SQLITE_PATH!"=="" set "SQLITE_PATH=stockstat.db"
set "SS_DB_URL=sqlite:///!SQLITE_PATH!"
goto :config_proxy

:config_pg
set /p "PG_HOST=PostgreSQL host [localhost]: "
if "!PG_HOST!"=="" set "PG_HOST=localhost"
set /p "PG_PORT=PostgreSQL port [5432]: "
if "!PG_PORT!"=="" set "PG_PORT=5432"
set /p "PG_DB=Database name [stockstat]: "
if "!PG_DB!"=="" set "PG_DB=stockstat"
set /p "PG_USER=Username [stockstat]: "
if "!PG_USER!"=="" set "PG_USER=stockstat"
set /p "PG_PASS=Password: "
set "SS_DB_URL=postgresql://!PG_USER!:!PG_PASS!@!PG_HOST!:!PG_PORT!/!PG_DB!"
goto :config_proxy

:config_custom_db
set /p "SS_DB_URL=DATABASE_URL: "

:config_proxy
echo.
set /p "INPUT_PROXY=Enable proxy? [y/N]: "
if /i not "!INPUT_PROXY!"=="y" goto :config_admin
set "SS_PROXY_ENABLED=true"
set /p "INPUT_PROXY_TYPE=Proxy type [http]: "
if not "!INPUT_PROXY_TYPE!"=="" set "SS_PROXY_TYPE=!INPUT_PROXY_TYPE!"
if /i "!SS_PROXY_TYPE!"=="http" (
    set "SS_PROXY_URL=http://127.0.0.1:8889"
) else (
    set "SS_PROXY_URL=socks5://127.0.0.1:1089"
)
set /p "INPUT_PROXY_URL=Proxy URL [!SS_PROXY_URL!]: "
if not "!INPUT_PROXY_URL!"=="" set "SS_PROXY_URL=!INPUT_PROXY_URL!"

:config_admin
echo.
set /p "INPUT_ADMIN=Enable web admin? [Y/n]: "
if /i "!INPUT_ADMIN!"=="n" set "SS_ADMIN_ENABLED=false"

echo.
set /p "INPUT_RELOAD=Enable hot reload (dev mode)? [y/N]: "
if /i "!INPUT_RELOAD!"=="y" set "SS_RELOAD=1"

echo.
echo === Configuration Summary ===
echo   Host:         !SS_HOST!
echo   Port:         !SS_PORT!
if not "!SS_DB_URL!"=="" (
    echo   Database:     !SS_DB_URL!
) else (
    echo   Database:     sqlite:///stockstat.db (default)
)
if not "!SS_REDIS_URL!"=="" echo   Redis:        !SS_REDIS_URL!
echo   Proxy:        !SS_PROXY_ENABLED!
if "!SS_PROXY_ENABLED!"=="true" echo   Proxy URL:    !SS_PROXY_URL!
echo   Admin UI:     !SS_ADMIN_ENABLED!
echo   Reload:       !SS_RELOAD!
echo.
set /p "CONFIRM=Start server? [Y/n]: "
if /i "!CONFIRM!"=="n" (
    echo Aborted.
    exit /b 0
)

:start_server

:: -- Set environment variables --
set "HOST=%SS_HOST%"
set "PORT=%SS_PORT%"
if not "%SS_DB_URL%"=="" set "DATABASE_URL=%SS_DB_URL%"
if not "%SS_REDIS_URL%"=="" set "REDIS_URL=%SS_REDIS_URL%"
set "STOCKSTAT_PROXY_ENABLED=%SS_PROXY_ENABLED%"
set "STOCKSTAT_PROXY_TYPE=%SS_PROXY_TYPE%"
set "STOCKSTAT_PROXY_URL=%SS_PROXY_URL%"
set "STOCKSTAT_ADMIN_ENABLED=%SS_ADMIN_ENABLED%"
set "STOCKSTAT_DEFAULT_SOURCE=%SS_DEFAULT_SOURCE%"

:: -- Check Python availability --
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH. Please install Python 3.10+.
    exit /b 1
)

:: -- Check backend package --
python -c "import stockstat_backend" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] stockstat_backend not installed.
    echo        Run: cd backend ^&^& pip install -e .
    exit /b 1
)

:: -- Determine display host --
set "DISPLAY_HOST=%SS_HOST%"
if "%SS_HOST%"=="0.0.0.0" set "DISPLAY_HOST=localhost"

:: -- Start server --
echo.
echo === Starting StockStat Backend ===
echo   Host:     %SS_HOST%
echo   Port:     %SS_PORT%
echo   Database: %DATABASE_URL%
echo   Admin:    http://%DISPLAY_HOST%:%SS_PORT%/admin/
echo   API:      http://%DISPLAY_HOST%:%SS_PORT%/api/v1/health
echo.

if "%SS_RELOAD%"=="1" (
    python -m uvicorn stockstat_backend.app:app --host %SS_HOST% --port %SS_PORT% --reload
) else (
    python -m uvicorn stockstat_backend.app:app --host %SS_HOST% --port %SS_PORT%
)
goto :eof

:show_help
echo.
echo StockStat Backend Service Startup Script
echo.
echo Usage:
echo   serve.bat                              Start with defaults
echo   serve.bat --config                     Interactive configuration
echo   serve.bat --host 0.0.0.0 --port 9000   Override host and port
echo   serve.bat --db-url "sqlite:///C:/data/stockstat.db"
echo   serve.bat --redis-url "redis://localhost:6379/0"
echo   serve.bat --proxy http http://127.0.0.1:8889
echo   serve.bat --no-admin                   Disable web admin UI
echo   serve.bat --reload                     Enable hot reload (dev mode)
echo   serve.bat --help                       Show this help
echo.
echo Options can be combined:
echo   serve.bat --config --reload
echo   serve.bat --host 0.0.0.0 --port 9000 --proxy socks5 socks5://127.0.0.1:1089
echo.
goto :eof
