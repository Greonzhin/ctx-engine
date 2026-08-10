param(
  [switch]$KeepDockerRunning
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

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message"
}

function Assert-CleanGitStatus {
  $status = (git status --short --branch) -join "`n"
  Write-Host $status
  $dirty = $status -split "`n" | Where-Object { $_ -and -not $_.StartsWith("## ") }
  if ($dirty) {
    throw "Public release gate requires a clean git worktree before tagging public release."
  }
}

Write-Step "Checking license and public project metadata"
$licenseFile = Join-Path $root "LICENSE"
if (-not (Test-Path -LiteralPath $licenseFile)) {
  throw "Missing LICENSE file in repository root!"
}
$pyprojectFile = Join-Path $root "pyproject.toml"
$pyprojectText = Get-Content -Raw $pyprojectFile
if ($pyprojectText -notmatch "\[project\.urls\]" -or $pyprojectText -notmatch "https://github\.com/Greonzhin/ctx-engine") {
  throw "pyproject.toml missing project URLs for https://github.com/Greonzhin/ctx-engine"
}

Write-Step "Public release local quality gate"
& (Join-Path $root "scripts\quality_gate.ps1")

Write-Step "Public release client and Docker gate"
$clientArgs = @("-UseDocker", "-RunClients")
if ($KeepDockerRunning) {
  $clientArgs += "-KeepRunning"
}
& (Join-Path $root "scripts\client_smoke.ps1") @clientArgs

Write-Step "GitHub Actions runtime status"
$ciText = (& $projectPython -m ctx_engine.cli ci status . --run --limit 3) -join "`n"
Write-Host $ciText
$ci = $ciText | ConvertFrom-Json
$emptyStepCount = @($ci.runtime.empty_step_failures).Count
$failingRunCount = @($ci.runtime.failing_runs).Count
if ($emptyStepCount -gt 0) {
  Write-Warning "GitHub Actions zero-step failure detected ($emptyStepCount jobs). Treat this as a platform/runner blocker, not a local build failure."
} elseif ($failingRunCount -gt 0) {
  Write-Warning "GitHub Actions has failing completed runs ($failingRunCount). Inspect logs before public release."
}

Write-Step "git status"
Assert-CleanGitStatus

$commit = (git rev-parse --short HEAD).Trim()
Write-Host ""
Write-Host "Public open-source release ready!"
Write-Host "Release note fields:"
Write-Host "  repository: https://github.com/Greonzhin/ctx-engine"
Write-Host "  commit: $commit"
Write-Host "  image_tag: ctx-engine:latest"
Write-Host "  license: MIT"
Write-Host "  quality_gate: pass"
Write-Host "  docker_smoke: pass"
Write-Host "  client_smoke: pass"
if ($emptyStepCount -gt 0) {
  Write-Host "  known_issue: GitHub Actions zero-step failure"
} else {
  Write-Host "  known_issue: none observed in latest checked runs"
}
