@echo off
chcp 65001 >nul 2>&1
title Quant Tuner

cd /d "%~dp0.."

REM Check if tuner already running
curl -s -m 3 http://127.0.0.1:5179/api/presets >nul 2>&1
if %errorlevel%==0 (
    echo [INFO] Tuner already running at http://localhost:5179
    echo Opening browser...
    start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" "http://localhost:5179"
    timeout /t 2 >nul
    exit /b
)

echo ============================================
echo   Quant Tuner - Incremental Update & Start
echo ============================================
echo.
echo [1/2] Updating ETF data (incremental)...
python -u scripts/quant_data_fetcher.py
if %errorlevel% neq 0 (
    echo [WARN] Data update failed, starting tuner anyway.
)

echo.
echo [2/2] Starting tuner server...
echo Opening browser...
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" "http://localhost:5179"
python -u scripts/quant_tuner.py

pause
