@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0.."
if not exist "scripts\preclose_push.py" (
    echo [ERROR] Cannot find scripts\preclose_push.py
    echo Current dir: %CD%
    echo Expected: %~dp0..
    pause
    exit /b 1
)

echo ========================================
echo   Pre-Close Push - %date% %time%
echo ========================================
echo.

python scripts\preclose_push.py
set EXITCODE=%ERRORLEVEL%

echo.
echo [%date% %time%] Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
