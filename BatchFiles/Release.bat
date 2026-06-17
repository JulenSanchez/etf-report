@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Version Release - ETF Report

cd /d "%~dp0.."

echo ============================================
echo   ETF Report - Version Release
echo   RELEASE_RUNBOOK semi-automated
echo ============================================
echo.

REM ===== Phase 0: Release Qualification =====
echo [Phase 0] Release Qualification
echo --------------------------------------------
echo Check Board.md: in_progress should be empty for release.
echo Check Board.md: no open/fixing critical/major bugs.
echo.
echo Press Ctrl+C to abort, or
pause

REM ===== Phase 1: Local Verification =====
echo.
echo [Phase 1] Local Verification
echo --------------------------------------------
echo Running update_report.py (no publish)...
python -u scripts/update_report.py
if %errorlevel% neq 0 (
    echo [ERROR] Report generation failed. Aborting.
    pause
    exit /b 1
)
echo [OK] Report generated successfully.
echo.

echo Audit checklist: docs\ops\audit.md
echo No automated audit script is currently configured.
echo Review audit checklist manually when needed before continuing.
echo.
pause

REM ===== Phase 2: Security Review =====
echo.
echo [Phase 2] Security Review
echo --------------------------------------------
echo Checking for sensitive content in staged changes...
echo.

REM Check for local paths
git diff --stat 2>nul
echo.
echo --- Scanning for local absolute paths ---
git diff 2>nul | findstr /i "C:\\Users\\ C:/Users/ file:///" >nul 2>&1
if %errorlevel%==0 (
    echo [WARN] Local absolute paths detected in diff! Review before proceeding.
    git diff 2>nul | findstr /i "C:\\Users\\ C:/Users/ file:///"
    echo.
) else (
    echo [OK] No local absolute paths found.
)

REM Check for secrets
git diff 2>nul | findstr /i "password secret token api_key webhook" >nul 2>&1
if %errorlevel%==0 (
    echo [WARN] Potential secrets detected in diff! Review carefully.
) else (
    echo [OK] No obvious secrets found.
)
echo.
pause

REM ===== Phase 3: .gitignore Check =====
echo.
echo [Phase 3] .gitignore Boundary Check
echo --------------------------------------------
echo Checking that sensitive files are NOT tracked...
set BOUNDARY_OK=1
git ls-files config/secrets.yaml 2>nul | findstr /r ".*" >nul 2>&1
if %errorlevel%==0 (
    echo [ERROR] config/secrets.yaml is tracked!
    set BOUNDARY_OK=0
)
if "%BOUNDARY_OK%"=="1" (
    echo [OK] Sensitive files are properly gitignored.
)
echo.
pause

REM ===== Phase 4: Version & Governance =====
echo.
echo [Phase 4] Version & Governance
echo --------------------------------------------
echo Current version in Board.md:
findstr /i "当前版本" plans\Board.md 2>nul
echo.
set /p VERSION="Enter new version (e.g. v2.7.0): "
if "%VERSION%"=="" (
    echo [ERROR] No version specified. Aborting.
    pause
    exit /b 1
)
echo Version: %VERSION%
echo.
echo IMPORTANT: Update these files manually before continuing:
echo   - plans/Board.md: clear done section, update version + date
echo   - plans/Archive.md: add version release record
echo.
pause

REM ===== Phase 5: Pre-push Check =====
echo.
echo [Phase 5] Pre-push Check
echo --------------------------------------------
git fetch origin 2>nul
echo.
echo Commits to be pushed:
git log origin/main..HEAD --oneline 2>nul
echo.
echo Diff summary vs origin/main:
git diff --stat origin/main HEAD 2>nul
echo.
pause

REM ===== Phase 6: Commit & Push =====
echo.
echo [Phase 6] Commit & Push
echo --------------------------------------------
echo Staging changes (current directory only)...
git add .

echo.
echo Staged files:
git status --short

echo.
set /p CONFIRM="Proceed with commit and push? (y/N): "
if /i not "%CONFIRM%"=="y" (
    echo Aborted.
    git reset HEAD >nul 2>&1
    pause
    exit /b 0
)

for /f "tokens=*" %%d in ('powershell -command "Get-Date -Format 'yyyy-MM-dd HH:mm'"') do set COMMIT_DATE=%%d
git commit -m "release: %VERSION% - %COMMIT_DATE%"
if %errorlevel% neq 0 (
    echo [INFO] Nothing new to commit. Pushing existing commits...
)

echo.
echo Pushing to origin/main...
git push origin main
if %errorlevel% neq 0 (
    echo [ERROR] Push failed!
    pause
    exit /b 1
)

REM ===== Phase 7: Post-release Verify =====
echo.
echo [Phase 7] Post-release Verify
echo --------------------------------------------
git log -1 --oneline
echo.
echo [DONE] %VERSION% released!
echo Check: https://julensanchez.github.io/etf-report/
echo.
pause
