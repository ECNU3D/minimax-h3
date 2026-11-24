param([int]$Port = 8321)
$ErrorActionPreference = 'Stop'
$directorRoot = $PSScriptRoot
$repoRoot = Split-Path -Parent $directorRoot
try {
    $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
    Write-Host "Director already running: http://127.0.0.1:$Port"
    exit 0
} catch { }
if (-not (Test-Path -LiteralPath (Join-Path $directorRoot 'node_modules'))) {
    Push-Location $directorRoot
    try { & npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' } } finally { Pop-Location }
}
Push-Location $directorRoot
try { & npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Build failed' } } finally { Pop-Location }
$directorData = Join-Path $directorRoot 'data'
New-Item -ItemType Directory -Force -Path $directorData | Out-Null
$pythonPath = Join-Path $repoRoot '.venv-cu130/Scripts/python.exe'
$process = Start-Process -FilePath $pythonPath -ArgumentList @('h3_director/server.py','--port',"$Port") -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $directorData 'server.stdout.log') -RedirectStandardError (Join-Path $directorData 'server.stderr.log') -PassThru
Write-Host "H3 Director started (PID $($process.Id)): http://127.0.0.1:$Port"
