param(
  [switch]$RunClients,
  [switch]$UseDocker,
  [switch]$KeepRunning
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

function Assert-GatewayHealth {
  $health = Invoke-WebRequest -Uri "http://127.0.0.1:7331/health" -UseBasicParsing -TimeoutSec 5
  if ($health.StatusCode -ne 200) {
    throw "Docker gateway health HTTP 200 donmedi: $($health.StatusCode)"
  }

  $dashboard = Invoke-WebRequest -Uri "http://127.0.0.1:7331/dashboard/status" -UseBasicParsing -TimeoutSec 5
  if ($dashboard.StatusCode -ne 200) {
    throw "Dashboard status HTTP 200 donmedi: $($dashboard.StatusCode)"
  }
}

$startedDocker = $false
try {
  if ($UseDocker) {
    Write-Step "Docker gateway build/run smoke"
    & (Join-Path $root "scripts\docker_smoke.ps1") -KeepRunning
    $startedDocker = $true

    Write-Step "Docker gateway health"
    Assert-GatewayHealth
  }

  Write-Step "adapter config status"
  & $projectPython -m ctx_engine.cli install status .

  Write-Step "client endpoint and CLI probe status"
  $clientCheckArgs = @("-m", "ctx_engine.cli", "client-check", ".", "--strict")
  if ($RunClients) {
    $clientCheckArgs += "--run"
  }
  & $projectPython @clientCheckArgs

  Write-Host ""
  Write-Host "Private beta manual client acceptance:"
  Write-Host "  Adapter config status: ctx install status ."
  Write-Host "  Endpoint match: ctx client-check . --strict --run"
  Write-Host "  Docker gateway health: http://127.0.0.1:7331/health"
  Write-Host "  Dashboard status: http://127.0.0.1:7331/dashboard/status"
  Write-Host "  Codex: open Codex chat and run /mcp"
  Write-Host "  Claude: claude mcp get ctx-engine"
  Write-Host "  Gemini: gemini mcp list"
} finally {
  if ($startedDocker -and -not $KeepRunning) {
    docker compose down | Out-Host
  }
}
