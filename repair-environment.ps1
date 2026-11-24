$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$uvExe = Join-Path $PSScriptRoot 'tools\uv.exe'
$pythonExe = Join-Path $PSScriptRoot 'tools\python\cpython-3.12.14-windows-x86_64-none\python.exe'
$active = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq (Join-Path $PSScriptRoot '.venv-cu130\Scripts\python.exe') }
if ($active) { throw 'Stop this project Python processes before repairing the environment.' }
if (-not (Test-Path -LiteralPath $uvExe)) { throw 'tools\uv.exe is missing. Restore it from the official astral-sh/uv distribution.' }
if (-not (Test-Path -LiteralPath $pythonExe)) {
    & $uvExe python install 3.12.14 --install-dir (Join-Path $PSScriptRoot 'tools\python') --no-bin
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed.' }
}
& $uvExe venv --python $pythonExe --allow-existing --seed .venv-cu130
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
& $uvExe pip install --python .venv-cu130\Scripts\python.exe -r docs\requirements-cu130-sage-lock.txt --extra-index-url https://download.pytorch.org/whl/cu130 --index-strategy unsafe-best-match
if ($LASTEXITCODE -ne 0) { throw 'Dependency restore failed.' }
& $uvExe pip check --python .venv-cu130\Scripts\python.exe
if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }
Write-Host 'Environment restored. Run h3_director\start.ps1 for the current INT8 production workflow.'
