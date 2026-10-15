' يشغّل البرنامج (وضع الشبكة) بدون نافذة سوداء
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
sh.Run "cmd /c chcp 65001 >nul & python launcher.py --lan", 0, False
