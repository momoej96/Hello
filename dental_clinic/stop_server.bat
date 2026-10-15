@echo off
chcp 65001 >nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*launcher.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Server stopped.
timeout /t 2 >nul
