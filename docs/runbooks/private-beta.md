# Private Beta Runbook

This runbook is for the private beta path: local Docker image, private GitHub repo, and real Codex/Claude/Gemini client checks. It does not publish to PyPI or Docker Hub.

## Setup

Prerequisites:

- Windows PowerShell.
- Python 3.12 available on PATH.
- Docker Desktop running with the Linux daemon reachable.
- Optional real client CLIs: Claude and Gemini. Codex is checked manually through `/mcp`.

Install locally:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ctx init
ctx index .
ctx install codex
ctx install claude
ctx install gemini
```

## Release Gate

Run the private beta gate from the repo root:

```powershell
.\scripts\private_beta_gate.ps1
```

The gate runs:

- `scripts/quality_gate.ps1`
- `scripts/client_smoke.ps1 -UseDocker -RunClients`
- `ctx ci status . --run --limit 3`
- `git status --short --branch`

The gate expects a clean git worktree before release tagging. It prints the release note fields:

- commit hash
- image tag: `ctx-engine:dev`
- quality gate result
- Docker smoke result
- client smoke result
- known issue status

## Client Acceptance

With the gateway running, verify:

```powershell
Invoke-WebRequest http://127.0.0.1:7331/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:7331/dashboard/status -UseBasicParsing
ctx install status .
ctx client-check . --strict --run
```

Manual client checks:

```powershell
claude mcp get ctx-engine
gemini mcp list
```

For Codex, open Codex and run `/mcp`; the expected endpoint is:

```text
http://127.0.0.1:7331/mcp
```

## Recovery

If port `7331` is busy or the gateway is unhealthy:

```powershell
docker compose down
docker ps
netstat -ano | findstr :7331
```

If the data mount fails, verify the host data directory:

```powershell
Test-Path "$env:USERPROFILE\.ctx-engine"
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ctx-engine"
```

If Docker Desktop is unreachable:

```powershell
docker context show
docker version
```

The expected container runtime posture is:

- host bind: `127.0.0.1:7331:7331`
- workspace mount: `/workspace:ro`
- data mount: `/data` writable
- container user: `10001:10001`

## GitHub Actions Zero-Step Troubleshooting

The private beta gate treats GitHub Actions jobs with `steps: []` as a platform/runner blocker, not as a local build failure. Local gates remain the source of truth until hosted runners execute workflow steps.

Check:

- Repository Actions are enabled.
- Billing or spending limit allows GitHub-hosted runners.
- Organization policy allows `windows-latest`, `ubuntu-latest`, and marketplace actions.
- Runner availability is not blocked by account or org settings.
- The failed job URL shows a runner/platform setup issue before checkout/setup steps start.

Command:

```powershell
ctx ci status . --run --limit 3
```

Relevant fields:

- `runtime.failing_runs`
- `runtime.job_diagnostics`
- `runtime.empty_step_failures`
