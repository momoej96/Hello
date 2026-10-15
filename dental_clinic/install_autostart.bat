@echo off
chcp 65001 >nul
set "SRC=%~dp0start_hidden.vbs"
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DentalClinic.lnk"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%'); $s.TargetPath='%SRC%'; $s.WorkingDirectory='%~dp0'; $s.Save()"
echo Done. The program will start automatically when Windows starts.
echo To remove: delete DentalClinic from the Startup folder (Win+R, shell:startup).
pause
