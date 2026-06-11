@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0.."
if not exist "scripts\update_report.py" (
    echo [ERROR] Cannot find scripts\update_report.py
    pause
    exit /b 1
)

echo ========================================
echo   Daily Report Update - %date% %time%
echo ========================================
echo.

python scripts\update_report.py --publish
set EXITCODE=%ERRORLEVEL%

echo.
echo [%date% %time%] Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
