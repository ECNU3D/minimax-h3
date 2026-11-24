# Scope PATH changes to this process. The vendored scripts remain unmodified.
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z_]+$')][string]$Tool,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$ToolArgs
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv-cu130\Scripts\python.exe'
$taskBin = Join-Path $taskRoot 'tools\ffmpeg-8.1.2\bin'
$taskScript = Join-Path $taskRoot "skills\ffmpeg-skill\scripts\$Tool.py"
if (-not (Test-Path -LiteralPath $taskScript)) { throw "Unknown skill tool: $Tool" }
if (-not (Test-Path -LiteralPath (Join-Path $taskBin 'ffprobe.exe'))) { throw 'Missing pinned FFmpeg runtime. See docs/video-editing-workflow.md.' }
$taskOldPath = $env:PATH
$taskOldOverwrite = $env:FFMPEG_SKILL_NO_OVERWRITE
$taskOldUtf8 = $env:PYTHONUTF8
try {
    $env:PATH = "$taskBin;$taskOldPath"
    $env:FFMPEG_SKILL_NO_OVERWRITE = '1'
    $env:PYTHONUTF8 = '1'
    & $taskPython $taskScript @ToolArgs
    $taskExit = $LASTEXITCODE
} finally {
    $env:PATH = $taskOldPath
    $env:FFMPEG_SKILL_NO_OVERWRITE = $taskOldOverwrite
    $env:PYTHONUTF8 = $taskOldUtf8
}
exit $taskExit
