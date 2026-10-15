@echo off
chcp 65001 >nul
cd /d "%~dp0"
python launcher.py --demo
if errorlevel 1 pause
