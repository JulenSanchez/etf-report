@echo off
chcp 65001 >nul 2>&1
title Agent Guide Notice - ETF Report

cd /d "%~dp0.."

echo ============================================
echo   ETF Report - Agent Guide Notice
echo ============================================
echo.

python -u scripts/setup_rules.py

echo.
pause
