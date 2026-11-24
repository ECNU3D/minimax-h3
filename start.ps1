param([switch]$ConservativeVRAM, [switch]$Cuda13, [ValidateRange(0, 12)][double]$VramHeadroom = 0, [switch]$LowMemory, [switch]$DisablePinnedMemory, [switch]$SageAttention, [switch]$KJNodes, [switch]$Krea2Edit)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$env:PYTHONUTF8 = '1'
# CUDA 13 is the shared H3 runtime. Keep -Cuda13 for existing launchers.
$pythonExe = Join-Path $taskRoot '.venv-cu130\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Missing .venv-cu130. See README.md and repair-environment.ps1.' }
try {
    $existing = Invoke-RestMethod 'http://127.0.0.1:8188/system_stats' -TimeoutSec 3
    Write-Host 'ComfyUI is already running at http://127.0.0.1:8188'
    Write-Host 'To change the environment or launch options, run stop.ps1 first.'
    return
} catch { }
$serverArgs = @('-u', 'main.py', '--listen', '127.0.0.1', '--port', '8188', '--disable-api-nodes', '--disable-all-custom-nodes', '--fast-disk', '--reserve-vram', '2', '--preview-method', 'none')
if ($ConservativeVRAM) {
    $serverArgs = @('-u', 'main.py', '--listen', '127.0.0.1', '--port', '8188', '--disable-api-nodes', '--disable-all-custom-nodes', '--fast-disk', '--disable-dynamic-vram', '--reserve-vram', '4', '--preview-method', 'none')
}
if ($VramHeadroom -gt 0) { $serverArgs += @('--vram-headroom', $VramHeadroom.ToString([System.Globalization.CultureInfo]::InvariantCulture)) }
if ($LowMemory) { $serverArgs += @('--disable-pinned-memory', '--disable-async-offload', '--disable-cuda-malloc') }
elseif ($DisablePinnedMemory) { $serverArgs += '--disable-pinned-memory' }
if ($SageAttention) { $serverArgs += '--use-sage-attention' }
$enabledCustomNodes = @()
if ($KJNodes) { $enabledCustomNodes += 'ComfyUI-KJNodes' }
if ($Krea2Edit) { $enabledCustomNodes += 'comfyui-krea2edit' }
if ($enabledCustomNodes.Count -gt 0) { $serverArgs += @('--whitelist-custom-nodes') + $enabledCustomNodes }
$process = Start-Process -FilePath $pythonExe -ArgumentList $serverArgs -WorkingDirectory (Join-Path $taskRoot 'ComfyUI') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot 'logs\comfy.stdout.log') -RedirectStandardError (Join-Path $taskRoot 'logs\comfy.stderr.log') -PassThru
$process.Id | Set-Content (Join-Path $taskRoot 'logs\comfy.pid')
Write-Host "Starting ComfyUI (PID $($process.Id)) at http://127.0.0.1:8188"
Write-Host 'Logs: logs\comfy.stderr.log'
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    try {
        $stats = Invoke-RestMethod 'http://127.0.0.1:8188/system_stats' -TimeoutSec 2
        Write-Host 'Ready: http://127.0.0.1:8188'
        return
    } catch { }
    $process.Refresh()
    if ($process.HasExited) { throw 'ComfyUI exited during startup. Read logs\comfy.stderr.log.' }
    Start-Sleep -Seconds 1
}
Write-Host 'Still starting. Check logs\comfy.stderr.log for progress.'
