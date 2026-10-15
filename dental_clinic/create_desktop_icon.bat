@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_desktop_icon.ps1"
echo.
echo Done. Double-click the tooth icon on the Desktop to open the program.
pause
