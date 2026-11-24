@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "h3_director\start.ps1"
start "" "http://127.0.0.1:8321"
