$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskInstall = Join-Path $taskRoot 'tools/qwen21'
$taskRun = Join-Path $taskRoot 'runs/qwen21-20260921'
try {
    $taskQueue = Invoke-RestMethod 'http://127.0.0.1:8190/queue' -TimeoutSec 3
    Write-Host 'Qwen test server is already listening at http://127.0.0.1:8190'
    return
} catch {}
$taskH3Queue = $null
try {
    $taskH3Queue = Invoke-RestMethod 'http://127.0.0.1:8188/queue' -TimeoutSec 3
} catch {}
if ($taskH3Queue -and ($taskH3Queue.queue_running.Count -or $taskH3Queue.queue_pending.Count)) {
    throw 'H3 has queued or running work. Wait for it to finish before using this GPU.'
}
$env:PYTHONUTF8 = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$taskArgs = @('main.py', '--listen', '127.0.0.1', '--port', '8190',
    '--disable-api-nodes', '--disable-all-custom-nodes', '--use-pytorch-cross-attention',
    '--reserve-vram', '2', '--preview-method', 'none',
    '--extra-model-paths-config', '../models.yaml')
$taskProcess = Start-Process -FilePath (Join-Path $taskInstall 'env/Scripts/python.exe') `
    -ArgumentList $taskArgs -WorkingDirectory (Join-Path $taskInstall 'ComfyUI') `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $taskRun 'comfy.stdout.log') `
    -RedirectStandardError (Join-Path $taskRun 'comfy.stderr.log')
Set-Content -LiteralPath (Join-Path $taskRun 'comfy.pid') -Value $taskProcess.Id
Write-Host "Started Qwen test server (PID $($taskProcess.Id)): http://127.0.0.1:8190"
$taskDeadline = (Get-Date).AddSeconds(45)
while ((Get-Date) -lt $taskDeadline) {
    try {
        $null = Invoke-RestMethod 'http://127.0.0.1:8190/system_stats' -TimeoutSec 2
        Write-Host 'Ready: http://127.0.0.1:8190'
        return
    } catch {}
    $taskProcess.Refresh()
    if ($taskProcess.HasExited) { throw "Qwen server exited. Read $taskRun/comfy.stderr.log" }
    Start-Sleep -Seconds 1
}
Write-Host "Server is still starting. Read $taskRun/comfy.stderr.log"
