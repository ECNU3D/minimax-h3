@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Cuda13 -Krea2Edit
start "" "http://127.0.0.1:8188"
pause
