@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Git Push - ETF Report

cd /d "%~dp0.."

echo ============================================
echo   Git Push - Push to Origin
echo ============================================
echo.

REM Show current status
echo [1/4] Current status:
git status --short
echo.

REM Stage changes (current directory only, not repo root)
echo [2/4] Staging changes (current directory only)...
git add .
if %errorlevel% neq 0 (
    echo [ERROR] Add failed.
    pause
    exit /b 1
)

REM Show what will be committed
echo.
echo --- Files staged ---
git diff --cached --name-status
echo.

REM Check if there is anything to commit
git diff --cached --quiet
if %errorlevel%==0 (
    echo [INFO] Nothing to commit. Pushing existing commits only...
) else (
    set /p CONFIRM_COMMIT="Commit and push these changes? (y/N): "
    if /i not "!CONFIRM_COMMIT!"=="y" (
        echo Aborted.
        git reset HEAD >nul 2>&1
        pause
        exit /b 0
    )
    REM Commit with timestamp
    for /f "tokens=*" %%d in ('powershell -command "Get-Date -Format 'yyyy-MM-dd HH:mm'"') do set COMMIT_DATE=%%d
    git commit -m "update: !COMMIT_DATE!"
    echo [OK] Committed.
)

echo.
echo [3/4] Pushing to origin/main...
set /p CONFIRM_PUSH="Push to origin/main? (y/N): "
if /i not "!CONFIRM_PUSH!"=="y" (
    echo Aborted.
    pause
    exit /b 0
)

git push origin main
if %errorlevel% neq 0 (
    echo [ERROR] Push failed. If remote has diverged, use 'git pull --rebase' first.
    pause
    exit /b 1
)

echo.
echo [4/4] Verifying...
git log --oneline -3
echo.
echo [DONE] Pushed to origin/main.
echo.
pause
