param(
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

function Invoke-Compose {
  param([string[]]$Arguments)
  & docker compose @Arguments
}

function Initialize-DataMount {
  $homeDir = $env:HOME
  if (-not $homeDir) {
    $homeDir = $env:USERPROFILE
  }
  if (-not $homeDir) {
    throw "HOME veya USERPROFILE bulunamadi; Docker /data mount hazirlanamadi"
  }

  $dataDir = Join-Path $homeDir ".ctx-engine"
  New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

  $isWindowsPlatform = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
  if (-not $isWindowsPlatform) {
    & chmod 777 $dataDir
  }
}

function Show-ComposeLogs {
  try {
    Write-Host ""
    Write-Host "==> docker compose logs ctx-engine"
    Invoke-Compose @("logs", "--no-color", "ctx-engine")
  } catch {
    Write-Warning "docker compose logs alinamadi: $_"
  }
}

function Wait-Health {
  $deadline = (Get-Date).AddSeconds(60)
  do {
    try {
      $response = Invoke-WebRequest -Uri "http://127.0.0.1:7331/health" -UseBasicParsing -TimeoutSec 2
      if ($response.StatusCode -eq 200) {
        return
      }
    } catch {
      Start-Sleep -Seconds 1
    }
  } while ((Get-Date) -lt $deadline)

  throw "ctx-engine health endpoint hazir olmadi: http://127.0.0.1:7331/health"
}

function Assert-ContainerRuntime {
  $uid = (Invoke-Compose @("exec", "-T", "ctx-engine", "python", "-c", "import os; print(f'{os.getuid()}:{os.getgid()}')")).Trim()
  if ($uid -ne "10001:10001") {
    throw "Container user beklenen 10001:10001 degil: $uid"
  }

  $workspace = (Invoke-Compose @("exec", "-T", "ctx-engine", "python", "-c", "from pathlib import Path; print(Path('/workspace/pyproject.toml').exists())")).Trim()
  if ($workspace -ne "True") {
    throw "/workspace mount dogrulanamadi"
  }

  $data = (Invoke-Compose @("exec", "-T", "ctx-engine", "python", "-c", "from pathlib import Path; p=Path('/data/.docker-smoke-write'); p.write_text('ok'); p.unlink(); print('ok')")).Trim()
  if ($data -ne "ok") {
    throw "/data yazilabilirlik dogrulanamadi"
  }

  $readonlyScript = @"
from pathlib import Path
p = Path('/workspace/.docker-smoke-write')
try:
    p.write_text('should-not-write')
    p.unlink(missing_ok=True)
    raise SystemExit('workspace-write-succeeded')
except OSError:
    print('readonly')
"@
  $workspaceMode = (Invoke-Compose @("exec", "-T", "ctx-engine", "python", "-c", $readonlyScript)).Trim()
  if ($workspaceMode -ne "readonly") {
    throw "/workspace read-only dogrulanamadi: $workspaceMode"
  }
}

$failed = $false
try {
  Write-Step "host data mount hazirlaniyor"
  Initialize-DataMount

  Write-Step "docker compose config"
  Invoke-Compose @("config") | Out-Host

  Write-Step "docker compose up --build -d"
  Invoke-Compose @("up", "--build", "-d") | Out-Host

  Write-Step "health endpoint bekleniyor"
  Wait-Health

  Write-Step "container runtime mount/user kontrolleri"
  Assert-ContainerRuntime

  Write-Step "MCP contract check"
  & $projectPython -m ctx_engine.cli mcp-check --endpoint "http://127.0.0.1:7331/mcp"

  Write-Step "doctor"
  & $projectPython -m ctx_engine.cli doctor

  Write-Host ""
  Write-Host "Docker smoke tamam."
} catch {
  $failed = $true
  Write-Host ""
  Write-Host "Docker smoke failed: $($_.Exception.Message)" -ForegroundColor Red
  Show-ComposeLogs
} finally {
  if (-not $KeepRunning) {
    Write-Step "docker compose down"
    Invoke-Compose @("down") | Out-Host
  } else {
    Write-Host ""
    Write-Host "KeepRunning aktif; container acik birakildi."
  }
}

if ($failed) {
  exit 1
}
