@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0.."

REM Get today's date
for /f %%i in ('powershell -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i

REM Skip non-trading days
python -c "import sys; sys.path.insert(0,'scripts'); from trading_calendar import is_trading_day; sys.exit(0 if is_trading_day() else 1)"
if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] Non-trading day. Skipping report publish.
    exit /b 0
)

REM Refresh data (in case 15:15 task was skipped)
echo Refreshing data for %TODAY%...
python scripts\quant_data_fetcher.py --start %TODAY% --end %TODAY%
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Data refresh failed, continuing with existing data...
)

echo ========================================
echo   Daily Report Publish - %date% %time%
echo ========================================

python scripts\update_report.py --publish
set EXITCODE=%ERRORLEVEL%

echo.
echo [%date% %time%] Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
