@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0.."

REM Get today's date
for /f %%i in ('powershell -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i

REM Skip non-trading days
python scripts\trading_calendar.py --is-trading-day
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] Non-trading day. Skipping.
    exit /b 0
)

REM Step 1: Full data refresh (gap fill + today)
echo ========================================
echo   Post-Market Data Refresh - %date% %time%
echo ========================================
python -u scripts\quant_data_fetcher.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Data refresh failed. Aborting.
    pause
    exit /b %ERRORLEVEL%
)

REM Step 2: Generate and publish report
echo.
echo ========================================
echo   Daily Report Publish - %date% %time%
echo ========================================

python scripts\update_report.py --publish
set EXITCODE=%ERRORLEVEL%

echo.
echo [%date% %time%] Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
