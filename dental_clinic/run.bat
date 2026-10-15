@echo off
chcp 65001 >nul
cd /d "%~dp0"
python launcher.py
if errorlevel 1 (
  echo.
  echo Python was not found. Install Python 3.9+ from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
)
