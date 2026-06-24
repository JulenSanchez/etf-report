@echo off
cd /d "%~dp0.."
python scripts\fetch_etf_metadata.py
pause
