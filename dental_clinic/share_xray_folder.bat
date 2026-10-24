@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Run on the SECOND computer (the one with the second X-ray sensor). Needs administrator rights.
net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0share_xray_folder.ps1"
echo.
pause
