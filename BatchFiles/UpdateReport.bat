@echo off
chcp 65001 >nul 2>&1
title Update ETF Report

cd /d "%~dp0.."

echo ============================================
echo   ETF Report - Daily Update & Publish
echo ============================================
echo.

python -u scripts/update_report.py --publish

echo.
if %errorlevel%==0 (
    echo [DONE] Report updated and published successfully.
) else (
    echo [ERROR] Update failed with code %errorlevel%.
)
echo.
pause
