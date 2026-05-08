@echo off
chcp 65001 >nul 2>&1
title Setup Rules - ETF Report

cd /d "%~dp0.."

echo ============================================
echo   ETF Report - Setup AI Rules
echo   (CodeBuddy .mdc / Claude Code .md)
echo ============================================
echo.

echo [1/2] Checking available rules...
python -u scripts/setup_rules.py --list

echo.
echo [2/2] Installing rules...
python -u scripts/setup_rules.py

echo.
pause
