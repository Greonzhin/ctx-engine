# ctx-engine

[![ci](https://github.com/Greonzhin/ctx-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/Greonzhin/ctx-engine/actions/workflows/ci.yml)

`ctx-engine` is a standalone, local-first MCP context gateway for Codex, Claude Code, and Gemini CLI.

P0 focuses on one reliable job: run a Dockerized read-only MCP gateway that indexes local code/docs, builds provenance-rich context capsules, keeps built-in SQLite memory, records an action ledger, and generates client adapters.

## P0 Scope

Implemented:

- HTTP MCP gateway at `http://127.0.0.1:7331/mcp`
- MCP protocol `2025-11-25` reporting with compatibility for older protocol headers
- CLI: `init`, `index`, `status`, `capsule`, `benchmark`, `retrieval-benchmark`, `pack-summary`, `blast-radius`, `semantic-refs`, `semantic-impact`, `docs`, `docs-scan`, `memory`, `install`, `client-check`, `security-scan`, `workflow`, `rules`, `hooks`, `feedback`, `skill-pack`, `cache`, `compress-log`, `doctor`, `egress-report`, `path`, `mcp`, `mcp-check`, `mcp-lint`, `inspector-smoke`, `serve`, `ledger`
- SQLite + FTS5 store for files, symbols, docs, memory, cache, and ledger
- Python / JavaScript / TypeScript indexing with Tree-sitter availability checks and safe AST/regex fallback
- Code/docs index hashes included in capsule cache keys with `ctx cache verify` evidence reports
- Local docs provider for README, AGENTS, CLAUDE, GEMINI, docs, ADR, architecture, runbooks, and OpenAPI files
- Context7 public-docs provider guard and cache; live fetch is opt-in with `CTX_ENGINE_CONTEXT7_LIVE=1`
- Prompt-injection scanner for local docs and Context7 public-doc snippets
- Context7 egress event logging with reportable hashes/latency/status
- Optional security scanner adapters for Semgrep, Gitleaks, Secretlint, npm audit, and pip-audit
- Built-in Hindsight-inspired memory: retain, recall, reflect, verify, supersede
- Internal RTK: token estimation, ranking, skeleton/snippet budget shaping
- Docker safe/dev/offline/audit modes
- Docker runtime uses a non-root UID/GID and loopback-only compose port publishing
- Codex, Claude, Gemini, and generic MCP adapter generation
- Windows / WSL2 / Docker path mapping checks
- Import-aware test plan suggestions in context capsules
- Built-in workflow recipes, generated-rules drift checks, safe hook advisory plans, capsule feedback, advisory skill pack generation, and deterministic log compression

Not implemented in P0:

- external Hindsight service as a required dependency (optional adapter exists; default remains SQLite)
- KuzuDB real backend as default (sqlite is default; optional backend path is additive)
- Neo4j
- dashboard
- policy engine
- verified semantic cache
- shell or write tools
- downstream untrusted MCP gatewaying

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Quick Start

```bash
ctx init
ctx index .
ctx capsule "where is auth handled?"
ctx benchmark "where is auth handled?"
ctx install codex
ctx install claude
ctx install gemini
ctx install status
ctx client-check --run
ctx security-scan . --all
ctx workflow suggest "fix failing auth test"
ctx rules check . --strict
ctx hooks plan all
ctx feedback report
ctx skill-pack generate fix-failing-test --format markdown
ctx cache verify --strict
ctx compress-log failing-test.log
ctx doctor --strict
ctx mcp-check
ctx mcp-lint --strict
ctx inspector-smoke
ctx docs-scan --strict
ctx egress-report --provider context7
ctx pack-summary "where is auth handled?"
ctx blast-radius "where is auth handled?"
ctx semantic-refs authenticate_request
ctx semantic-impact "where is auth handled?" --include-tests
ctx retrieval-benchmark . --top-k 3
ctx serve --mode safe
```

All clients point to:

```text
http://127.0.0.1:7331/mcp
```

## Docker

Build locally:

```bash
docker build -t ctx-engine:dev .
```

Run with the workspace mounted read-only:

```bash
docker run --rm \
  --name ctx-engine \
  -p 127.0.0.1:7331:7331 \
  -v "$PWD:/workspace:ro" \
  -v "$HOME/.ctx-engine:/data" \
  ctx-engine:dev
```

The container listens on `0.0.0.0` internally so Docker port publishing works; publish to `127.0.0.1` on the host for the intended local-only posture. The image runs as UID/GID `10001:10001`.

On Windows PowerShell, run the Docker runtime smoke when Docker Desktop is available:

```powershell
.\scripts\docker_smoke.ps1
```

The smoke builds the compose image, waits for `http://127.0.0.1:7331/health`, verifies the MCP endpoint from the host, checks the non-root container user, confirms `/workspace` is read-only, confirms `/data` is writable, and then runs `docker compose down` unless `-KeepRunning` is passed.

Additional local verification helpers:

```powershell
.\scripts\client_smoke.ps1 -UseDocker -RunClients
.\scripts\external_runtime_smoke.ps1
.\scripts\quality_gate.ps1
```

`client_smoke.ps1` verifies generated adapter status and can run installed Codex/Claude/Gemini client probes. `external_runtime_smoke.ps1` verifies Kuzu and reports optional Hindsight/LSP/SCIP runtime probes when their environment variables are configured.
`quality_gate.ps1` runs the local P1 gate; pass `-RunSecurityScanners` to require installed Semgrep and Gitleaks.

## MCP Tools

P0 exposes only read/context tools:

- `workspace_register(path)`
- `workspace_list()`
- `index_repository(workspace_id)`
- `search_symbols(query)`
- `get_file_skeleton(path)`
- `get_symbol_context(symbol_name)`
- `get_symbol_references(symbol_name, workspace_id?, depth?, limit?)`
- `get_change_impact(query, workspace_id?, depth?, limit?, include_tests?)`
- `get_blast_radius(query, workspace_id?, depth?, limit?)`
- `get_context_capsule(query, token_budget=4000, include_docs=true)`
- `resolve_docs_context(query)`
- `write_session_memory(content, files=[], symbols=[], docs=[])`
- `read_session_memory(query="", scope="project")`
- `get_action_ledger(query="")`
- `get_doctor_status()`

No shell execution or repository write tools are exposed.

## Roadmap

See [Other Repositories And Adoptable Ideas](docs/research/other-repos-and-adoptables.md) for the current comparison against adjacent MCP gateways, code-context engines, memory tools, and token-reduction projects.

See [Context7 Project Scan](docs/research/context7-project-scan.md) for the latest public-doc scan of ctx-engine dependencies and client integration surfaces.

See [Expanded Sources And Untested Follow-Up](docs/research/expanded-sources-and-untested-followup.md) for the research pass over the expanded source list and the remaining untested validation items.

See [Current Gap Analysis](docs/research/current-gap-analysis-2026-05-16.md) for the latest review of gaps, improvement opportunities, and updated P0.5/P1/P2 priorities.

See [Memory And Graph Repo Scan](docs/research/memory-and-graph-repo-scan-2026-05-19.md) for the detailed comparison of localmem, mnemo-cortex, HoloCortex, graphify, code-review-graph, ast-grep, and Hindsight.

P1 candidates:

- MCP descriptor hash registry and allowlist quality gate
- workflow recipes and local quality gate script
- optional scanner adapters: Semgrep, Gitleaks, Secretlint, npm audit, and pip-audit
- test suggestion engine refinements
- capsule feedback
- advisory skill pack generator
- rules drift detection and deterministic terminal log compression
- Codex/Claude/Gemini safe hook advisory plans; executable hook install remains current-doc-gated
- egress reports and rules drift checks

P2 optional paths now present behind explicit opt-in or local verification:

- LSP/SCIP semantic ingestion (`CTX_ENGINE_LSP_*`, `CTX_ENGINE_SCIP_*`)
- optional KuzuDB backend selected with `CTX_ENGINE_GRAPH_BACKEND=kuzu`; SQLite remains the default and fallback
- external Hindsight adapter selected with `CTX_ENGINE_MEMORY_PROVIDER=hindsight`; SQLite remains the default and fallback
- verified capsule cache reports via `ctx cache verify`; capsule cache remains local SQLite

Remaining P2 candidates:

- dashboard
- policy engine
- multi-project workspace manager

These remain outside the P0 default path; optional P2 integrations must be explicitly enabled.

## Verification

```bash
pytest
scripts/smoke.sh
ctx doctor
ctx doctor --strict
ctx install status
ctx client-check
ctx security-scan . --all
ctx workflow list
ctx rules check . --strict
ctx hooks plan all
ctx feedback report
ctx skill-pack list
ctx cache verify --strict
ctx compress-log failing-test.log
ctx mcp-check
ctx mcp-lint
ctx inspector-smoke
ctx docs-scan --strict
ctx egress-report
ctx pack-summary "where is auth handled?"
ctx blast-radius "where is auth handled?"
ctx semantic-refs authenticate_request
ctx semantic-impact "where is auth handled?" --include-tests
ctx retrieval-benchmark . --top-k 3
pytest -q tests/test_semantic_quality_gate.py
ctx benchmark "where is auth handled?"
scripts/docker_smoke.ps1
scripts/client_smoke.ps1
scripts/external_runtime_smoke.ps1
scripts/quality_gate.ps1
```

Semantic ingest toggles (optional):

```bash
# LSP file/command/rpc/session options
export CTX_ENGINE_LSP_EDGE_FILE=/path/to/lsp_edges.jsonl
export CTX_ENGINE_LSP_EDGE_COMMAND="python emit_edges.py"
export CTX_ENGINE_LSP_RPC_COMMAND="python lsp_rpc_bridge.py"
export CTX_ENGINE_LSP_CLIENT_COMMAND="pylsp --stdio"

# SCIP file/command/index options
export CTX_ENGINE_SCIP_EDGE_FILE=/path/to/scip_edges.jsonl
export CTX_ENGINE_SCIP_EDGE_COMMAND="python emit_scip_edges.py"
export CTX_ENGINE_SCIP_INDEX_FILE=/path/to/index.scip
export CTX_ENGINE_SCIP_PRINT_COMMAND="scip"

# Optional external hindsight runtime (default provider is sqlite)
export CTX_ENGINE_MEMORY_PROVIDER=hindsight
export CTX_ENGINE_HINDSIGHT_ENDPOINT=http://127.0.0.1:8787

# Optional graph backend
export CTX_ENGINE_GRAPH_BACKEND=kuzu
```

To verify a running HTTP gateway without Docker, start `ctx serve --mode safe` in one terminal and run:

```bash
ctx mcp-check --endpoint http://127.0.0.1:7331/mcp
```

Suggested local quality gate:

```bash
pytest
ctx docs-scan --strict
ctx egress-report --provider context7
ctx pack-summary "where is auth handled?"
```
