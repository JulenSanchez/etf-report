@echo off
chcp 65001 >nul 2>&1
title Git Pull - ETF Report

cd /d "%~dp0.."

echo ============================================
echo   Git Pull - Sync with Origin
echo ============================================
echo.

REM Stash local changes before pull to avoid data loss
echo [1/3] Stashing local changes (if any)...
git stash push -m "auto-stash before pull %date% %time%" 2>nul
if %errorlevel%==0 (
    echo [OK] Local changes stashed. Use 'git stash pop' to restore.
) else (
    echo [OK] No local changes to stash.
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
echo [3/3] Resetting to origin/main...
echo WARNING: This will overwrite all local tracked files with origin/main.
set /p CONFIRM="Continue? (y/N): "
if /i not "%CONFIRM%"=="y" (
    echo Aborted. Use 'git stash pop' to restore stashed changes.
    pause
    exit /b 0
)

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
