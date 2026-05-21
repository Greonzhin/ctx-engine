param(
  [switch]$SkipDocker,
  [switch]$RunSecurityScanners
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $root

$projectPython = $env:CTX_ENGINE_PYTHON
if (-not $projectPython) {
  $windowsVenvPython = Join-Path $root ".venv\Scripts\python.exe"
  $posixVenvPython = Join-Path $root ".venv/bin/python"
  if (Test-Path -LiteralPath $windowsVenvPython) {
    $projectPython = $windowsVenvPython
  } elseif (Test-Path -LiteralPath $posixVenvPython) {
    $projectPython = $posixVenvPython
  } else {
    $projectPython = "python"
  }
}

$testTmp = "C:\ctx-engine-tmp\pytest-" + [guid]::NewGuid().ToString("N")
New-Item -ItemType Directory -Force -Path $testTmp | Out-Null

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message"
}

Write-Step "full pytest"
& $projectPython -m pytest -q --basetemp $testTmp

Write-Step "semantic quality gate"
& $projectPython -m pytest -q --basetemp $testTmp tests/test_semantic_quality_gate.py tests/test_retrieval_benchmark.py

Write-Step "mcp lint strict"
& $projectPython -m ctx_engine.cli mcp-lint --strict

Write-Step "rules drift strict"
& $projectPython -m ctx_engine.cli rules check . --strict

Write-Step "workflow recipes"
& $projectPython -m ctx_engine.cli workflow list

Write-Step "hook advisory plan"
& $projectPython -m ctx_engine.cli hooks plan all

Write-Step "capsule feedback report"
& $projectPython -m ctx_engine.cli feedback report --limit 5

Write-Step "skill pack generator"
& $projectPython -m ctx_engine.cli skill-pack generate fix-failing-test

Write-Step "log compression smoke"
$sampleLog = Join-Path $testTmp "sample-log.txt"
@"
============================= FAILURES =============================
FAILED tests/test_auth.py::test_authenticate_request_accepts_valid_token
Traceback (most recent call last):
  AssertionError: expected valid token
docker compose failed with permission denied
"@ | Set-Content -Path $sampleLog -Encoding UTF8
& $projectPython -m ctx_engine.cli compress-log $sampleLog

Write-Step "workspace index for docs gate"
$indexText = (& $projectPython -m ctx_engine.cli index .) -join "`n"
Write-Host $indexText
$indexPayload = $indexText | ConvertFrom-Json
$workspaceId = $indexPayload.code.workspace_id

Write-Step "verified capsule cache"
& $projectPython -m ctx_engine.cli cache verify $workspaceId --strict

Write-Step "docs scan strict"
& $projectPython -m ctx_engine.cli docs-scan --strict

Write-Step "context7 egress report"
& $projectPython -m ctx_engine.cli egress-report --provider context7

if ($RunSecurityScanners) {
  Write-Step "optional security scanners strict"
  & $projectPython -m ctx_engine.cli security-scan . --all --strict
}

if (-not $SkipDocker) {
  Write-Step "docker smoke"
  & (Join-Path $root "scripts\docker_smoke.ps1")
}

Write-Host ""
Write-Host "Quality gate tamam."
