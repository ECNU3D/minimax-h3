@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Cuda13 -SageAttention -KJNodes -VramHeadroom 8
pause
