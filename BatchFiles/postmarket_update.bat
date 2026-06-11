@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0.."
if not exist "scripts\quant_data_fetcher.py" (
    echo [ERROR] Cannot find scripts\quant_data_fetcher.py
    pause
    exit /b 1
)

echo ========================================
echo   Post-Market Data Update - %date% %time%
echo ========================================
echo.

python scripts\quant_data_fetcher.py --incremental
set EXITCODE=%ERRORLEVEL%

echo.
echo [%date% %time%] Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
