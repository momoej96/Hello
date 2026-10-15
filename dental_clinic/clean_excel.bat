@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo اسحب ملف Excel وأفلته فوق هذا الملف clean_excel.bat
  pause
  exit /b
)
python clean_excel.py "%~1"
pause
