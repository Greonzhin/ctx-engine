# Expanded Sources And Untested Follow-Up

Date: 2026-05-21

Input source: `C:\Users\Sanal-Ofis\Drive'ım\Projeler\Klon\RESEARCH_SOURCES_EXPANDED.md`

Scope: research the expanded source list and clarify items that were not fully tested in the current local environment. This document does not widen P0. It turns the source list into adoption and validation decisions.

## Current Tested Baseline

Already tested locally:

- Python package install: `pip install -e ".[dev]"`
- Unit/integration tests: full suite passes on Python 3.12
- CLI index/capsule/memory/docs/install/doctor/path smoke
- HTTP `/health` server smoke
- MCP contract smoke: in-process `ctx mcp-check`
- MCP contract smoke: live HTTP `ctx mcp-check --endpoint ...` against a temporary local `ctx serve`
- MCP metadata lint: `ctx mcp-lint`
- MCP Inspector smoke command: `ctx inspector-smoke`
- Adapter install status: `ctx install status`
- Client status: `ctx client-check`
- Code/docs index hash cache invalidation for capsules
- Local token benchmark: `ctx benchmark`
- Dockerfile/compose runtime hardening: non-root UID/GID, loopback-only compose publish, healthcheck, `.dockerignore`
- Docker build/run smoke: `scripts/docker_smoke.ps1`
- Context7 live query path after updating to `query-docs`
- Context7 SSE `data:` response parsing
- Gemini adapter generation using `mcpServers.ctx-engine.httpUrl`

Not tested locally:

- Real Codex interactive `/mcp` connection to `ctx-engine`.
- MCP Inspector CLI/UI against `ctx-engine`.
- Official MCP Python SDK client session against `ctx-engine`.
- External tools such as Vexp, Serena, Repomix, CodeGraphContext, Hindsight, RTK, Semgrep, Gitleaks, Trivy, OSV, promptfoo, RAGAS.

## P0 Shortlist Findings

| Source | Researched Finding | ctx-engine Decision | Validation Status |
|---|---|---|---|
| Vexp docs/changelog | Local-first context engine with tree-sitter, SQLite graph, compact capsules, session memory, manifest hashes, multi-agent setup, and context-token reduction claims. | Keep capsule-first architecture. Add benchmark discipline, manifest/index hash, and broader adapter status later. | Researched only; not installed. |
| Serena | LSP/JetBrains-backed symbol navigation, references, refactoring, symbolic edits, memory, per-project config. Also exposes shell/read/edit tools that overlap with agent harnesses. | Adopt semantic retrieval ideas in P2. Do not expose shell/write/refactor tools through ctx-engine P0. | Researched only; not installed. |
| CodeGraphContext | MCP + CLI local code graph, graph DB backends, optional SCIP, broad client setup wizard. | Useful P1/P2 reference for graph query UX and adapter wizard. Keep KuzuDB/SCIP out of P0. | Researched only; not installed. |
| Repomix | AI-friendly repo packing, Tree-sitter compression, token count tree, Secretlint security check enabled by default. | Adopt token-count tree, local-only pack-summary fallback, and secret-check UX in P1. Do not pack/upload private source by default. | Researched only; not installed. |
| localmem | Local-first multi-agent memory MCP with hybrid retrieval and temporal triples; broad MCP tool set and optional dashboard. | Borrow lifecycle/namespace concepts for built-in memory only. | Researched only; not installed. |
| mnemo-cortex | Session watcher ingestion and cross-agent synthesis workflow across multiple coding agents. | Borrow synthesis/session-ingestion patterns for optional adapters only. | Researched only; not installed. |
| HoloCortex | Federated P2P graph memory with signed deltas and trust-aware contradiction handling. | Borrow provenance/conflict-ranking ideas in P2 experiments. | Researched only; not installed. |
| graphify | Multimodal graph extraction and confidence labeling (`EXTRACTED/INFERRED/AMBIGUOUS`). | Add confidence labels in ctx artifacts and keep model-optional core path. | Researched only; not installed. |
| code-review-graph | Incremental graph and blast-radius context narrowing for code review workflows. | Add blast-radius query primitive and retrieval quality benchmark discipline. | Researched only; not installed. |
| ast-grep | Structural AST search/lint/rewrite engine with broad installer support. | Evaluate optional structural-search adapter for precision retrieval rules. | Researched only; not installed. |
| Context7 | Current MCP tools are `resolve-library-id` and `query-docs`; HTTP Streamable endpoint returns SSE event frames. | Done: updated client to `query-docs`, added SSE parsing and known library mappings. | Live query tested. |
| Codex MCP/AGENTS/Hooks | Codex `config.toml` supports HTTP MCP `url`, `enabled_tools`, timeouts; AGENTS discovery has global/project precedence; hooks can intercept MCP tool calls but are guardrails, not full enforcement. | Current Codex config is aligned. Add adapter status and P1 hook generator later. | Docs researched; real Codex client not tested. |
| Claude Code MCP/Memory/Hooks | Claude supports HTTP MCP config and `.mcp.json`; settings include managed allowlists; hooks and HTTP hooks exist for lifecycle/tool events. | Current Claude adapter is acceptable. Add status validation and hook research in P1. | Docs researched; real Claude client not tested. |
| Gemini CLI MCP/Config | HTTP MCP server config uses `httpUrl`; `GEMINI.md` is a context file; settings support sandbox/tool exclusions. | Done: Gemini adapter now emits `httpUrl`. | Adapter file tested; real Gemini client not tested. |
| MCP Transports/Security | Streamable HTTP is current production transport; origin validation, least privilege, auth, and tool review are important. | Current HTTP local daemon is directionally correct. Add Inspector/SDK conformance later. | Local and live-HTTP JSON-RPC smoke tested. |
| Tree-sitter Queries | Queries are better than regex fallback for stable symbol extraction. | Use Tree-sitter query patterns for JS/TS/Python in P1. | Current P0 uses AST/regex fallback plus parser availability check. |
| Codebase-Memory paper | Persistent Tree-sitter MCP graph with parallel indexing, call graph traversal, impact analysis, community detection, and reported token/tool-call reductions. | Adopt benchmark shape and graph-native query targets later. Keep P0 simple. | Paper researched; no implementation added. |

## Untested Items From Previous Work

| Item | Why Untested | What We Learned | Next Test |
|---|---|---|---|
| Docker build/run | Previously blocked by an unhealthy Docker Desktop engine. | Home machine now validates build/run through `scripts/docker_smoke.ps1`; image, health endpoint, MCP contract, non-root user, read-only workspace, and writable data mount are verified. | Keep Docker smoke in CI/local quality gate. |
| Real Codex MCP connection | Codex CLI is installed, but no stable non-interactive MCP status probe is configured. | Config shape matches official `mcp_servers.*.url` docs and adapter status passes. | Start `ctx serve` or Docker smoke, then run Codex `/mcp` manually. |
| Real Claude MCP connection | Claude Code client was invoked in this workspace. | `.mcp.json` HTTP config is aligned with Claude docs and `claude mcp get ctx-engine` reported Connected. | Keep in `scripts/client_smoke.ps1 -UseDocker -RunClients`. |
| Real Gemini MCP connection | Gemini CLI was invoked in this workspace. | `httpUrl` is the correct HTTP field; `gemini mcp list` reported `ctx-engine` Connected. | Keep in `scripts/client_smoke.ps1 -UseDocker -RunClients`; track the Windows libuv assertion emitted after listing. |
| MCP Inspector | Inspector can now be run via `ctx inspector-smoke --run` when `npx` is available. | Inspector supports Streamable HTTP and CLI `tools/list`. | Use `ctx inspector-smoke --run --strict` against active endpoint. |
| MCP Python SDK client | SDK not added to dev dependencies. | SDK supports Streamable HTTP sessions, `initialize`, `list_tools`, `call_tool`, and session headers. | Add optional dev extra and conformance smoke, or keep custom JSON-RPC until needed. |
| External Hindsight | Explicitly out of P0. | Hindsight now has local MCP and many memory tools, but it requires external service shape/LLM/database assumptions. | P1/P2 adapter only; keep built-in SQLite memory for P0. |
| Serena/CodeGraphContext | They introduce LSP/SCIP/graph DB/write/shell surfaces outside P0. | Strong references for semantic retrieval and graph UX. | P2 comparison install in isolated fixture repo. |
| Repomix | Not required for P0 and would add Node dependency. | Compression/security/token tree ideas are useful. | P1 local-only `ctx pack-summary` or benchmark inspiration. |
| Security scanners | Semgrep/Gitleaks/Trivy/OSV are P1 audit adapters. | Add adapters only when audit mode grows beyond storage/logging. | P1 fixture suite with malicious docs/secrets. |
| Prompt/eval tooling | RAGAS/promptfoo/SWE-bench not needed for P0. | Need a lightweight capsule-quality benchmark first. | P0.5 `ctx benchmark` before external eval frameworks. |

## Adoption Queue

P0.5, safe to do before P1:

- Done: add `ctx install status` for Codex/Claude/Gemini/generated snippets.
- Done: add MCP contract smoke for in-process and running HTTP endpoints.
- Done: add `ctx mcp-lint` for tool metadata/schema checks.
- Done: add `ctx inspector-smoke` for optional MCP Inspector CLI smoke.
- Done: add code/docs index hash and capsule cache invalidation.
- Done: add `ctx benchmark` for token counts: full repo baseline, selected files, skeleton/snippet/doc/memory budget, omitted context.
- Done: add `ctx doctor --strict` to fail CI/local checks when warnings or unhealthy status exist.
- Done: add Docker non-root user, loopback-only compose publish, healthcheck, `.dockerignore`, and runtime smoke.
- Done: add GitHub Actions CI quality gate.
- Done: add client and external runtime smoke entrypoint scripts.

P1:

- Tree-sitter query-based symbol extraction.
- Better local retrieval scoring: BM25/FTS + symbol/path weighting + route/test/source links.
- Repomix-like local pack summary with secret checks and token count tree.
- Context7 version detection and egress report.
- Prompt-injection scanner for local docs and public docs results.
- Scanner adapters: Gitleaks/Semgrep/OSV/Trivy as optional audit hooks.

P2:

- LSP/SCIP ingestion opt-in paths exist; keep validating real LSP/SCIP binaries through smoke scripts.
- Optional Kuzu graph backend exists behind `CTX_ENGINE_GRAPH_BACKEND=kuzu`.
- Dashboard/policy engine.
- External Hindsight adapter.
- Multi-project workspace manager.

## Keep-Out Rules Confirmed

- Do not expose shell tools through ctx-engine.
- Do not expose repo write/edit/refactor tools through ctx-engine.
- Do not add external Hindsight service to P0.
- Do not add KuzuDB, LSP, SCIP, dashboard, policy engine, or verified semantic cache in P0.
- Do not proxy downstream untrusted MCP servers before descriptor hash and allowlist exist.
- Do not send private code, private docs, secrets, proprietary snippets, internal OpenAPI specs, or full prompts to Context7.

## Sources Checked

- Vexp docs: https://vexp.dev/docs
- Vexp changelog: https://vexp.dev/changelog
- Serena: https://github.com/oraios/serena
- CodeGraphContext: https://github.com/CodeGraphContext/CodeGraphContext
- Repomix: https://github.com/yamadashy/repomix
- Repomix configuration: https://repomix.com/guide/configuration
- Context7: https://github.com/upstash/context7
- Codex MCP: https://developers.openai.com/codex/mcp
- Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- Codex Hooks: https://developers.openai.com/codex/hooks
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- Claude Code settings: https://code.claude.com/docs/en/settings
- Claude Code hooks: https://code.claude.com/docs/en/hooks
- Gemini CLI MCP: https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md
- MCP Inspector: https://modelcontextprotocol.io/docs/tools/inspector
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Codebase-Memory paper: https://arxiv.org/abs/2603.27277
- Hindsight MCP docs: https://docs.hindsight.vectorize.io/mcp/
- Hindsight local MCP guide: https://hindsight.vectorize.io/guides/2026/04/16/guide-run-hindsight-as-a-local-mcp-server
- RTK discussion reference: https://github.com/rtk-ai/rtk
- localmem: https://github.com/jordanaftermidnight/localmem
- mnemo-cortex: https://github.com/GuyMannDude/mnemo-cortex
- HoloCortex: https://github.com/Arkay92/HoloCortex
- graphify: https://github.com/safishamsi/graphify
- code-review-graph: https://github.com/tirth8205/code-review-graph
- ast-grep: https://github.com/ast-grep/ast-grep
