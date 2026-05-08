@echo off
chcp 65001 >nul 2>&1
title Fetch ETF Data

cd /d "%~dp0.."

echo ============================================
echo   ETF Data - Incremental Update
echo ============================================
echo.

python -u scripts/quant_data_fetcher.py

echo.
if %errorlevel%==0 (
    echo [DONE] Data updated successfully.
) else (
    echo [ERROR] Data update failed with code %errorlevel%.
)
echo.
pause
