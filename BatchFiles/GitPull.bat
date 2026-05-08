@echo off
chcp 65001 >nul 2>&1
title Git Pull - ETF Report

cd /d "%~dp0.."

echo ============================================
echo   Git Pull - Force Overwrite Local
echo ============================================
echo.
echo [1/2] Fetching from origin...
git fetch --all --prune
if %errorlevel% neq 0 (
    echo [ERROR] Fetch failed.
    pause
    exit /b 1
)

echo.
echo [2/2] Resetting to origin/main (force overwrite)...
git reset --hard origin/main
if %errorlevel% neq 0 (
    echo [ERROR] Reset failed.
    pause
    exit /b 1
)

echo.
echo [DONE] Local is now in sync with origin/main.
echo.
git log --oneline -3
echo.
pause
