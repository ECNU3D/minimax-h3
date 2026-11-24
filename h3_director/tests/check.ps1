$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $appRoot
$pythonExe = Join-Path $repoRoot '.venv-cu130/Scripts/python.exe'
$env:PYTHONUTF8 = '1'
Push-Location $repoRoot
try {
    foreach ($test in @('scripts/test_production_tools.py', 'scripts/test_h3_submission.py', 'scripts/test_audio_resume.py')) {
        & $pythonExe $test
        if ($LASTEXITCODE -ne 0) { throw "Failed: $test" }
    }
    & $pythonExe -m unittest discover -s h3_director/tests -p 'test_*.py'
    if ($LASTEXITCODE -ne 0) { throw 'Director unit tests failed' }
    & $pythonExe h3_director/tests/api_smoke.py --isolated
    if ($LASTEXITCODE -ne 0) { throw 'Isolated API smoke failed' }
    & node --check h3_director/agent/harness.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Agent JavaScript syntax failed' }
    & node --check h3_director/agent/optimize-prompt.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Prompt optimizer JavaScript syntax failed' }
    & node --check h3_director/agent/parse-storyboard.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Parser JavaScript syntax failed' }
    & node --check h3_director/agent/reference-dependencies.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Reference dependency agent syntax failed' }
    & node --test h3_director/tests/agent_runtime.test.mjs h3_director/tests/progress.test.mjs h3_director/tests/review_policy.test.mjs h3_director/tests/parse_checkpoint.test.mjs h3_director/tests/lab_prompts.test.mjs h3_director/tests/queue_policy.test.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Agent provider runtime checks failed' }
} finally { Pop-Location }
Write-Host 'Offline checks passed. No production submissions or model API calls.'
