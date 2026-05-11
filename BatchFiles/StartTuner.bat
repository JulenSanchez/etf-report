@echo off
chcp 65001 >nul 2>&1

REM User-facing double-click entry. Real launcher logic lives in StartTuner.ps1.
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0StartTuner.ps1"
exit /b 0
