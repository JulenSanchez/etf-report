@echo off
cd /d "%~dp0\.."
echo Starting Quant Tuner on http://localhost:5179 ...
start "Quant Tuner" cmd /k "python scripts\quant_tuner.py"
