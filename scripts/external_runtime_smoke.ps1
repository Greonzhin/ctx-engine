param(
  [string]$HindsightEndpoint = $env:CTX_ENGINE_HINDSIGHT_ENDPOINT,
  [switch]$StrictOptional
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

function New-TestTmp {
  return "C:\ctx-engine-tmp\pytest-" + [guid]::NewGuid().ToString("N")
}

function Invoke-Optional {
  param(
    [string]$Name,
    [scriptblock]$Body
  )
  try {
    Write-Host ""
    Write-Host "==> $Name"
    & $Body
  } catch {
    if ($StrictOptional) {
      throw
    }
    Write-Warning "$Name atlandi veya basarisiz: $_"
  }
}

Invoke-Optional "Kuzu real-runtime smoke" {
  $env:CTX_ENGINE_GRAPH_BACKEND = "kuzu"
  & $projectPython -m pytest -q --basetemp (New-TestTmp) tests/test_semantic_graph.py -k kuzu
}

Invoke-Optional "External Hindsight endpoint contract smoke" {
  if (-not $HindsightEndpoint) {
    throw "CTX_ENGINE_HINDSIGHT_ENDPOINT ayarlanmamis"
  }
  $env:CTX_ENGINE_MEMORY_PROVIDER = "hindsight"
  $env:CTX_ENGINE_HINDSIGHT_ENDPOINT = $HindsightEndpoint
  & $projectPython -c "from ctx_engine.integrations.hindsight import HindsightAdapter; a=HindsightAdapter(); ok, reason=a.status(); print({'available': ok, 'reason': reason, 'endpoint': a.endpoint}); raise SystemExit(0 if ok else 1)"
}

Invoke-Optional "Configured LSP semantic smoke" {
  if (-not ($env:CTX_ENGINE_LSP_EDGE_FILE -or $env:CTX_ENGINE_LSP_EDGE_COMMAND -or $env:CTX_ENGINE_LSP_RPC_COMMAND -or $env:CTX_ENGINE_LSP_CLIENT_COMMAND)) {
    throw "CTX_ENGINE_LSP_* ayari bulunmadi"
  }
  $env:CTX_ENGINE_SEMANTIC_LSP = "1"
  $env:CTX_ENGINE_SEMANTIC_SCIP = "0"
  & $projectPython -m ctx_engine.cli index tests/fixtures/python_app | Out-Null
  & $projectPython -m ctx_engine.cli semantic-refs authenticate_request
}

Invoke-Optional "Configured SCIP semantic smoke" {
  if (-not ($env:CTX_ENGINE_SCIP_EDGE_FILE -or $env:CTX_ENGINE_SCIP_EDGE_COMMAND -or $env:CTX_ENGINE_SCIP_INDEX_FILE -or $env:CTX_ENGINE_SCIP_PRINT_COMMAND)) {
    throw "CTX_ENGINE_SCIP_* ayari bulunmadi"
  }
  $env:CTX_ENGINE_SEMANTIC_LSP = "0"
  $env:CTX_ENGINE_SEMANTIC_SCIP = "1"
  & $projectPython -m ctx_engine.cli index tests/fixtures/python_app | Out-Null
  & $projectPython -m ctx_engine.cli semantic-refs authenticate_request
}

Write-Host ""
Write-Host "External runtime smoke tamam."
