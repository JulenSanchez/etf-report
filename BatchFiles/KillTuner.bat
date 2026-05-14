@echo off
chcp 65001 >nul
echo Killing Tuner processes...
wmic process where "commandline like '%%quant_tuner%%'" delete 2>nul
echo Done.
pause
