@echo off
chcp 65001 >nul 2>&1

cd /d "%~dp0.."

REM Get today's date in reliable yyyy-MM-dd format
for /f %%i in ('powershell -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i

echo ========================================
echo   Post-Market Data Refresh - %date% %time%
echo ========================================

python scripts\quant_data_fetcher.py --start %TODAY% --end %TODAY%
set EXITCODE=%ERRORLEVEL%

echo.
echo [%date% %time%] Exit code: %EXITCODE%
pause
exit /b %EXITCODE%
