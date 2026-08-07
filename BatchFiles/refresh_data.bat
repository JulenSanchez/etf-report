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

REM Post-market data refresh (Sina batch fast path for 1-day gaps, ~2s)
echo ========================================
echo   Post-Market Data Refresh - %date% %time%
echo ========================================
python -u scripts\quant_data_fetcher.py
set EXITCODE=%ERRORLEVEL%

echo.
echo [%date% %time%] Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
