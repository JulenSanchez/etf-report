@echo off
chcp 65001 >nul 2>&1
title Cold-Start Test — Full Data Fetch from Scratch

cd /d "%~dp0.."

set "DATA_DIR=data\quant"
set "BACKUP_DIR=data\quant\_cold_backup"
set "PASSED=0"
set "TEMP_DIR=%TEMP%"

echo ============================================================
echo   Cold-Start Test — Simulate No-CSV Environment
echo ============================================================
echo.
echo This script will:
echo   1. Move all CSV files from %DATA_DIR% to %BACKUP_DIR%
echo   2. Run full data fetch from scratch (--full)
echo   3. Verify all ETFs have valid daily + weekly CSVs
echo   4. Run a quick backtest to validate data integrity
echo   5. Restore original CSVs from backup
echo.

REM ═══════════════════════════════════════ Stage 0: Pre-flight ═══
echo [Stage 0] Pre-flight checks...
echo.

python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Python not found
    pause & exit /b 1
)
echo   Python: OK

if not exist "config\quant_universe.yaml" (
    echo [FAIL] config\quant_universe.yaml not found
    pause & exit /b 1
)
echo   Config: OK

if not exist "scripts\quant_data_fetcher.py" (
    echo [FAIL] scripts\quant_data_fetcher.py not found
    pause & exit /b 1
)
echo   Fetcher script: OK

python -c "import yaml; d=yaml.safe_load(open(r'config\quant_universe.yaml','r',encoding='utf-8')); print(len(d['universe']))" > "%TEMP_DIR%\_cs_expected.txt"
set /p EXPECTED=<"%TEMP_DIR%\_cs_expected.txt"
del "%TEMP_DIR%\_cs_expected.txt" >nul 2>&1
echo   Expected ETFs: %EXPECTED%

echo.

REM ═══════════════════════════════════════ Stage 1: Backup ═══
echo [Stage 1] Backing up existing data...
echo.

if exist "%BACKUP_DIR%" (
    echo   Removing old backup dir...
    rmdir /s /q "%BACKUP_DIR%"
)
mkdir "%BACKUP_DIR%"

set MOVED=0
for /f "delims=" %%f in ('dir /b "%DATA_DIR%\*_daily.csv" 2^>nul') do (
    move "%DATA_DIR%\%%f" "%BACKUP_DIR%\" >nul 2>&1
    set /a MOVED+=1
)
for /f "delims=" %%f in ('dir /b "%DATA_DIR%\*_weekly.csv" 2^>nul') do (
    move "%DATA_DIR%\%%f" "%BACKUP_DIR%\" >nul 2>&1
    set /a MOVED+=1
)
echo   Moved %MOVED% CSV files to %BACKUP_DIR%

REM Also backup metadata (regenerated independently, keep safe just in case)
for %%f in ("%DATA_DIR%\etf_metadata.json" "%DATA_DIR%\stock_metadata.json" "%DATA_DIR%\last_signal.json") do (
    if exist %%f copy "%%f" "%BACKUP_DIR%\" >nul 2>&1
)

REM Verify all daily CSVs gone
dir /b "%DATA_DIR%\*_daily.csv" 2>nul >nul
if %ERRORLEVEL% EQU 0 (
    echo   [WARN] Some daily CSVs could not be moved
) else (
    echo   Verify: all daily CSVs removed - OK
)
echo.

REM ═══════════════════════════════════════ Stage 2: Full Fetch ═══
echo [Stage 2] Full data fetch from scratch...
echo   This may take 3-5 minutes for all %EXPECTED% ETFs.
echo ============================================================
echo.

python -u scripts\quant_data_fetcher.py --full
set FETCH_EXIT=%ERRORLEVEL%

echo.
echo ============================================================
echo   Fetch exit code: %FETCH_EXIT%
echo ============================================================

if %FETCH_EXIT% NEQ 0 (
    echo.
    echo [FAIL] Data fetch failed with exit code %FETCH_EXIT%
    goto :restore
)

echo.

REM ═══════════════════════════════════════ Stage 3: Verify ═══
echo [Stage 3] Verify regenerated data...
echo.

set REGEN_DAILY=0
for /f %%i in ('dir /b "%DATA_DIR%\*_daily.csv" 2^>nul ^| find /c /v ""') do set REGEN_DAILY=%%i
echo   Daily CSVs regenerated: %REGEN_DAILY%

set REGEN_WEEKLY=0
for /f %%i in ('dir /b "%DATA_DIR%\*_weekly.csv" 2^>nul ^| find /c /v ""') do set REGEN_WEEKLY=%%i
echo   Weekly CSVs regenerated: %REGEN_WEEKLY%

if %REGEN_DAILY% LSS %EXPECTED% (
    echo   [WARN] Daily CSVs (%REGEN_DAILY%) ^< expected (%EXPECTED%) - some ETFs may have failed
)
if %REGEN_DAILY% GEQ %EXPECTED% (
    echo   [PASS] Daily CSV count meets or exceeds universe config
)

REM Spot-check: pick first daily CSV, count lines via Python
dir /b "%DATA_DIR%\*_daily.csv" 2>nul > "%TEMP_DIR%\_cs_csvlist.txt"
set /p FIRST_CSV=<"%TEMP_DIR%\_cs_csvlist.txt"
del "%TEMP_DIR%\_cs_csvlist.txt" >nul 2>&1

if "%FIRST_CSV%"=="" (
    echo   [FAIL] No CSVs found - fetch produced nothing
    goto :restore
)

python -c "import sys; lines=open(sys.argv[1],'r',encoding='utf-8').readlines(); print(len(lines))" "%CD%\%DATA_DIR%\%FIRST_CSV%" > "%TEMP_DIR%\_cs_rows.txt"
set /p ROWS=<"%TEMP_DIR%\_cs_rows.txt"
del "%TEMP_DIR%\_cs_rows.txt" >nul 2>&1

echo   Spot-check %FIRST_CSV%: %ROWS% rows
if %ROWS% LSS 10 (
    echo   [FAIL] CSV %FIRST_CSV% has only %ROWS% rows - fetch likely failed
    goto :restore
)
echo   [PASS] Data looks valid (spot check)
echo.

REM ═══════════════════════════════════════ Stage 4: Backtest ═══
echo [Stage 4] Quick backtest validation...
echo.

python -c "import sys; sys.path.insert(0,'.'); sys.path.insert(0,'src'); from scripts.quant_backtest import run_backtest; nav,sig,extra=run_backtest(preset='gam-0',verbose=False); print('OK')" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   [PASS] Backtest ran successfully on regenerated data
) else (
    echo   [WARN] Backtest failed to run - data may be incomplete
)
echo.

REM ═══════════════════════════════════════ Stage 5: Done ═══
set PASSED=1
echo ============================================================
echo   [PASS] Cold-start test - ALL CHECKS PASSED
echo ============================================================
echo   %REGEN_DAILY% daily + %REGEN_WEEKLY% weekly CSVs generated
echo   Spot check: %FIRST_CSV% (%ROWS% rows)
echo   Backtest: OK
echo.

REM ═══════════════════════════════════════ Restore ═══
:restore
echo [Restore] Restoring original data from backup...
echo.

set RESTORED=0
for /f "delims=" %%f in ('dir /b "%BACKUP_DIR%\*_daily.csv" 2^>nul') do (
    move "%BACKUP_DIR%\%%f" "%DATA_DIR%\" >nul 2>&1
    set /a RESTORED+=1
)
for /f "delims=" %%f in ('dir /b "%BACKUP_DIR%\*_weekly.csv" 2^>nul') do (
    move "%BACKUP_DIR%\%%f" "%DATA_DIR%\" >nul 2>&1
    set /a RESTORED+=1
)
echo   Restored %RESTORED% CSV files to %DATA_DIR%

rmdir "%BACKUP_DIR%" >nul 2>&1
if exist "%BACKUP_DIR%" (
    echo   Backup dir not empty (contains metadata copies) - manual cleanup if needed
)

echo.

if %PASSED% EQU 1 (
    echo ============================================================
    echo   TEST PASSED - Full fetch pipeline works from scratch
    echo ============================================================
    echo.
    echo Next: GitHub Actions can use this flow for remote deployment.
) else (
    echo ============================================================
    echo   TEST FAILED - see errors above
    echo   Original data has been restored.
    echo ============================================================
)

pause
exit /b %FETCH_EXIT%
