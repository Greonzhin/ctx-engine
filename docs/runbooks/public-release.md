# Public Open-Source Release Runbook

This runbook outlines the process for packaging, verifying, and publishing `ctx-engine` as a public open-source project hosted at `https://github.com/Greonzhin/ctx-engine`.

## Prerequisites

- Python 3.11+ (Python 3.12 recommended).
- Docker Desktop running with Linux containers reachable.
- Windows PowerShell or POSIX shell (`bash`/`zsh`).
- Optional Client CLIs: Claude CLI, Gemini CLI, Codex.

## Quick Setup

```bash
git clone https://github.com/Greonzhin/ctx-engine.git
cd ctx-engine
python -m venv .venv
source .venv/bin/activate  # On Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Public Release Gate

Before tagging a public release or submitting major PRs, run the public release gate script:

On Windows PowerShell:

```powershell
.\scripts\public_release_gate.ps1
```

The gate script performs:

1. **License & Metadata Check**: Verifies presence of `LICENSE` (MIT) and valid repository URLs in `pyproject.toml`.
2. **Quality Gate (`scripts/quality_gate.ps1`)**:
   - `pytest` unit test suite
   - `ctx docs-scan --strict`
   - `ctx egress-report --provider context7`
   - `ctx mcp-lint --strict`
   - `ctx cache verify --strict`
   - `ctx doctor --strict`
3. **Docker & Client Smoke (`scripts/client_smoke.ps1`)**:
   - Builds container image `ctx-engine:dev`
   - Runs health checks on `http://127.0.0.1:7331/health` and `/dashboard/status`
   - Validates generated MCP adapters for Codex, Claude, and Gemini
4. **GitHub Actions Status Check**:
   - Checks recent CI status via `ctx ci status . --run --limit 3`
5. **Clean Worktree Check**:
   - Ensures `git status` reports no untracked or uncommitted modifications before release tagging.

## Publishing & Tagging

1. Ensure all tests pass and worktree is clean:
   ```bash
   git status
   ```
2. Tag the release:
   ```bash
   git tag -a v0.1.0 -m "Release v0.1.0"
   git push origin main --tags
   ```

## Client Integration Posture

All supported client agents (Codex, Claude Code, Gemini CLI) communicate via the local HTTP gateway endpoint:

```text
http://127.0.0.1:7331/mcp
```

The local dashboard status endpoint is accessible at:

```text
http://127.0.0.1:7331/dashboard
```

## License

This project is licensed under the MIT License - see the [LICENSE](../../LICENSE) file for details.
