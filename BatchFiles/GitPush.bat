@echo off
chcp 65001 >nul 2>&1
title Git Push - ETF Report

cd /d "%~dp0.."

echo ============================================
echo   Git Push - Force Push to Origin
echo ============================================
echo.

REM Show current status
echo [1/3] Current status:
git status --short
echo.

REM Stage all changes
echo [2/3] Staging all changes...
git add -A
if %errorlevel% neq 0 (
    echo [ERROR] Add failed.
    pause
    exit /b 1
)

REM Check if there is anything to commit
git diff --cached --quiet
if %errorlevel%==0 (
    echo [INFO] Nothing to commit. Pushing existing commits only...
) else (
    REM Commit with timestamp
    for /f "tokens=*" %%d in ('powershell -command "Get-Date -Format 'yyyy-MM-dd HH:mm'"') do set COMMIT_DATE=%%d
    git commit -m "update: %COMMIT_DATE%"
    echo [OK] Committed.
)

echo.
echo [3/3] Force pushing to origin/main...
git push --force --no-verify origin main
if %errorlevel% neq 0 (
    echo [ERROR] Push failed.
    pause
    exit /b 1
)

echo.
echo [DONE] Force pushed to origin/main.
echo.
git log --oneline -3
echo.
pause
