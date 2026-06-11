@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0.."
if not exist "scripts\preclose_push.py" (
    echo [ERROR] Cannot find scripts\preclose_push.py
    pause
    exit /b 1
)

echo ========================================
echo   Post-Market Data Refresh - %date% %time%
echo ========================================
echo.

python scripts\preclose_push.py --refresh-only
set EXITCODE=%ERRORLEVEL%

echo.
echo [%date% %time%] Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
