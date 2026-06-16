@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Git Pull - ETF Report

cd /d "%~dp0.."

echo ============================================
echo   Git Pull - Sync with Origin
echo ============================================
echo.

echo [1/3] Checking working tree...
set HAS_CHANGES=0
git status --short
for /f %%i in ('git status --porcelain') do set HAS_CHANGES=1
if "!HAS_CHANGES!"=="1" (
    echo.
    echo [WARN] Local changes detected. This script will not overwrite them.
    echo Commit/stash/discard manually, then run GitPull again.
    pause
    exit /b 1
)

echo.
echo [2/3] Fetching from origin...
git fetch --all --prune
if %errorlevel% neq 0 (
    echo [ERROR] Fetch failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Fast-forward pull...
git pull --ff-only origin main
if %errorlevel% neq 0 (
    echo [ERROR] Pull failed. Remote may have diverged; resolve manually.
    pause
    exit /b 1
)

echo.
echo [DONE] Local is now in sync with origin/main.
git log --oneline -3
echo.
pause
