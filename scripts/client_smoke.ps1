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

$startedDocker = $false
try {
  if ($UseDocker) {
    & (Join-Path $root "scripts\docker_smoke.ps1") -KeepRunning
    $startedDocker = $true
  }

  & $projectPython -m ctx_engine.cli install status .

  $clientCheckArgs = @("-m", "ctx_engine.cli", "client-check", ".", "--strict")
  if ($RunClients) {
    $clientCheckArgs += "--run"
  }
  & $projectPython @clientCheckArgs

  Write-Host ""
  Write-Host "Manual client checks when real CLIs are installed:"
  Write-Host "  Codex: open Codex chat and run /mcp"
  Write-Host "  Claude: claude mcp get ctx-engine"
  Write-Host "  Gemini: gemini mcp list"
} finally {
  if ($startedDocker -and -not $KeepRunning) {
    docker compose down | Out-Host
  }
}
