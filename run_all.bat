@echo off
chcp 936 >nul
title Motor Fault Diagnosis - Quick Start

echo ================================================
echo   Motor Fault Diagnosis System
echo ================================================
echo.

REM === CONFIG: set your emqx\bin path here ===
set "PROJECT_DIR=%~dp0"
set "EMQX_BIN=E:\emqx-5.3.2-windows-amd64\bin"

REM === [0] EMQX ===
echo [0/4] Starting EMQX...
curl -s http://localhost:18083 >nul 2>&1
if errorlevel 1 (
    echo   Launching EMQX from: %EMQX_BIN%
    start "EMQX" /D "%EMQX_BIN%" emqx.cmd console
    echo   Waiting 15 seconds...
    timeout /t 15 /nobreak >nul
) else (
    echo   EMQX is already running
)

REM === [1] Flask API ===
echo.
echo [1/4] Starting Flask API...
cd /d "%PROJECT_DIR%"
start "Flask API" cmd /k "venv\Scripts\python src\app.py --port 5000"
timeout /t 3 /nobreak >nul

REM === [2] Consumer ===
echo [2/4] Starting Consumer...
start "Consumer" cmd /k "venv\Scripts\python src\consumer.py"
timeout /t 3 /nobreak >nul

REM === [3] Producer ===
echo [3/4] Starting Producer...
start "Producer" cmd /k "venv\Scripts\python src\producer.py --no-loop"

REM === [4] Dashboard ===
echo [4/4] Starting Dashboard...
cd /d "%PROJECT_DIR%dashboard"
start "Dashboard" cmd /k "npm run dev"

echo.
echo ================================================
echo   All done! Open http://localhost:3000
echo.
echo   Running windows:
echo     - EMQX Broker
echo     - Flask API     (port 5000)
echo     - Consumer      (inference)
echo     - Producer      (data sender)
echo     - Dashboard     (port 3000)
echo.
echo   Ctrl+C each window to stop.
echo ================================================
pause
