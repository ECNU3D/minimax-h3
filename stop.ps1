$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'logs\comfy.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host 'No managed ComfyUI PID found.'; return }
$comfyPid = [int](Get-Content -LiteralPath $pidFile)
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$comfyPid"
$allowedPython = @((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'), (Join-Path $PSScriptRoot '.venv-cu130\Scripts\python.exe'))
if ($process -and $process.CommandLine -like '*main.py*' -and $process.ExecutablePath -in $allowedPython) {
    $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $comfyPid -and $_.Name -eq 'python.exe' -and $_.CommandLine -like '*main.py*' }
    foreach ($child in $children) { Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue }
    Stop-Process -Id $comfyPid -ErrorAction SilentlyContinue
    Write-Host "Stopped ComfyUI PID $comfyPid"
} elseif ($process) { throw 'PID belongs to a different process; refusing to stop it.' }
