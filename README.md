# ctx-engine

[![ci](https://github.com/Greonzhin/ctx-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/Greonzhin/ctx-engine/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP Protocol](https://img.shields.io/badge/MCP-2025--11--25-green.svg)](https://modelcontextprotocol.io/)

`ctx-engine` is a standalone, local-first MCP (Model Context Protocol) context gateway for coding agents including **Codex**, **Claude Code**, and **Gemini CLI**.

It runs a Dockerized read-only MCP gateway that indexes local code & documentation, builds provenance-rich context capsules, maintains built-in SQLite memory, tracks action ledgers, and generates client configuration adapters.

---

## Architecture Overview

```text
+-------------------------------------------------------------------------+
|                          AI Coding Clients                              |
|           [Codex CLI]       [Claude Code]       [Gemini CLI]            |
+-------------------------------------------------------------------------+
                                    |
                                    | (MCP HTTP / SSE / JSON-RPC)
                                    v
+-------------------------------------------------------------------------+
|                   ctx-engine Context Gateway                            |
|                   http://127.0.0.1:7331/mcp                             |
+-------------------------------------------------------------------------+
     |                 |                   |                   |
     v                 v                   v                   v
[Tree-sitter AST] [SQLite FTS5]    [Hindsight Memory]  [Security Scanners]
 (Code Graph)     (Full-Text Index) (Retain / Recall)  (Prompt/Secret Scan)
```

---

## Core Capabilities

- **HTTP MCP Gateway**: Compliant with MCP Protocol `2025-11-25` at `http://127.0.0.1:7331/mcp`.
- **Local AST & Code Graph**: Python, JavaScript, and TypeScript indexing powered by Tree-sitter with AST fallback.
- **SQLite + FTS5 Search**: High-performance full-text search with BM25 ranking across codebase symbols, comments, and local docs.
- **Hindsight Memory Store**: Built-in memory operations (`retain`, `recall`, `reflect`, `verify`, `supersede`) persisted in SQLite.
- **Security & Safety First**: Read-only design. Includes prompt-injection detection and optional security scanner adapters (Semgrep, Gitleaks, Secretlint, npm audit, pip-audit).
- **Docker Isolation**: Runs under non-root UID/GID (`10001:10001`) with read-only workspace mounts and host-loopback port binding (`127.0.0.1:7331`).
- **Client Adapters**: One-command generator and installer for Codex, Claude Code, and Gemini CLI configs.
- **Local Web Dashboard**: Read-only monitoring dashboard at `http://127.0.0.1:7331/dashboard`.

---

## Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/Greonzhin/ctx-engine.git
cd ctx-engine

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows PowerShell: .\.venv\Scripts\Activate.ps1

# Install in development mode
pip install -e ".[dev]"
```

### Basic Workflow

```bash
# Initialize local database and index current directory
ctx init
ctx index .

# Generate context capsule for a query
ctx capsule "where is auth handled?"

# Install client adapters
ctx install codex
ctx install claude
ctx install gemini
ctx install status

# Start HTTP gateway
ctx serve --mode safe
```

All connected clients communicate with `http://127.0.0.1:7331/mcp`.

---

## Docker Deployment

Build and run locally with workspace mounted read-only:

```bash
# Build Docker image
docker build -t ctx-engine:latest .

# Run container bound to loopback interface
docker run --rm \
  --name ctx-engine \
  -p 127.0.0.1:7331:7331 \
  -v "$PWD:/workspace:ro" \
  -v "$HOME/.ctx-engine:/data" \
  ctx-engine:latest
```

On Windows PowerShell, run the Docker smoke verification script:

```powershell
.\scripts\docker_smoke.ps1
```

---

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CTX_ENGINE_HOST` | `127.0.0.1` | Host interface for HTTP server |
| `CTX_ENGINE_PORT` | `7331` | Port for HTTP server and dashboard |
| `CTX_ENGINE_DATA_DIR` | `~/.ctx-engine` | Storage location for SQLite databases |
| `CTX_ENGINE_GRAPH_BACKEND` | `sqlite` | Graph backend (`sqlite` or `kuzu`) |
| `CTX_ENGINE_MEMORY_PROVIDER` | `sqlite` | Memory provider (`sqlite` or `hindsight`) |
| `CTX_ENGINE_CONTEXT7_LIVE` | `0` | Enable live remote Context7 doc fetches |

---

## Roadmap & Research

See the following research documents for comparison against adjacent MCP gateways, dependency scans, gap analyses, and priorities:

- [Other Repositories And Adoptable Ideas](docs/research/other-repos-and-adoptables.md)
- [Context7 Project Scan](docs/research/context7-project-scan.md)
- [Expanded Sources And Untested Follow-Up](docs/research/expanded-sources-and-untested-followup.md)
- [Current Gap Analysis](docs/research/current-gap-analysis-2026-05-16.md)
- [Memory And Graph Repo Scan](docs/research/memory-and-graph-repo-scan-2026-05-19.md)

---

## Verification & Release Gates

Run local quality and release validation gates:

```powershell
# Run unit test suite
pytest

# Run quality gate
.\scripts\quality_gate.ps1

# Run public release gate
.\scripts\public_release_gate.ps1
```

---

## Documentation & Runbooks

- [Public Open-Source Release Runbook](docs/runbooks/public-release.md)
- [Private Beta Runbook](docs/runbooks/private-beta.md)
- [Gap Analysis & Roadmap](docs/research/current-gap-analysis-2026-05-16.md)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
