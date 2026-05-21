# Current Gap Analysis

Date: 2026-05-21

Scope: review the current `ctx-engine` implementation against the latest public MCP/client/security/code-context references. This is a research and prioritization note only; it does not expand P0 or implement P1/P2 features.

## Current Local Baseline

- Tests pass locally with Python 3.12.
- Docker Desktop is healthy on the home machine; `scripts/docker_smoke.ps1` verifies build, health, MCP contract, non-root UID/GID, `/workspace:ro`, and writable `/data`.
- Dockerless checks still work: `ctx mcp-check`, `ctx install status`, `ctx benchmark`, temporary HTTP endpoint check.
- P0 safety boundary remains intact: no shell tools, no repository write/edit/refactor tools, no required external Hindsight service, no default KuzuDB backend, no dashboard/policy engine/verified semantic cache.

## Highest Priority Gaps

| Priority | Gap | Why It Matters Now | Suggested Scope |
|---|---|---|---|
| Done P0.5 | MCP protocol drift | The latest MCP specification is `2025-11-25`; `ctx-engine` now reports it while accepting older `2025-06-18` / `2025-03-26` headers for compatibility. | Keep monitoring client compatibility. |
| Done P0.5 | Streamable HTTP conformance details | The spec says Streamable HTTP uses POST and GET on one MCP endpoint; if the server does not offer SSE on GET, it should return `405`. | Done: `GET /mcp` now returns `405`; POST mcp-check sends protocol and Accept headers. |
| Done P0.5 | DNS rebinding hardening | MCP security guidance explicitly calls out Origin validation and localhost binding. | Done: Origin/Host checks now parse exact local hosts instead of prefix matching. |
| Done P0.5 | Inspector / official SDK smoke | Custom JSON-RPC smoke is useful but not enough. MCP Inspector is the current developer workflow for capability negotiation, tool schemas, tool calls, resources, prompts, logs, and edge cases. | Done: `ctx inspector-smoke` now provides optional `npx`-based Inspector `tools/list` smoke. |
| Done P0.5 | Real client verification | Codex, Claude Code, and Gemini config files are generated and parsed; `ctx client-check` now reports adapter status and optional safe local client probes. Claude Code and Gemini CLI were verified connected on this home machine. | Codex CLI is installed, but still needs manual `/mcp` because no stable non-interactive MCP status probe is configured. Gemini reports connected while still emitting a Windows libuv assertion after listing. |
| Done P0.5 | Docker hardening and runtime smoke | Docker docs and gateway practice emphasize isolation, restricted privileges, logging, and lifecycle control. | Done: Dockerfile/compose use UID/GID `10001:10001`, loopback-only publishing, compose healthcheck, `.dockerignore`, and `scripts/docker_smoke.ps1`. |

## Better But Still Simple

| Area | Current State | Improvement |
|---|---|---|
| Done P0.5 | Tool descriptions | Tools have concise descriptions, and metadata quality is now checked by `ctx mcp-lint`. | Keep iterating lint rules with real client/tooling feedback. |
| Tool naming | Names are readable and read/context-only. | Re-check against latest MCP tool-name guidance before protocol bump. |
| Origin/CORS | Invalid Origin returns 403 with exact local-host parsing. | Add direct browser/DNS-rebinding regression notes if a browser test harness is added. |
| Protocol headers | `mcp-check` sends `MCP-Protocol-Version`; server rejects unsupported versions. | Add SDK/Inspector validation next. |
| Done P0.5 | Error model | Tool input validation errors are now separated from protocol errors. | Done: `tools/call` returns `isError=true` tool execution results for model-correctable argument issues; malformed JSON-RPC remains protocol error. |
| Done P0.5 | Capsule cache | Index hash prevents stale capsules and re-index now clears only the affected workspace capsule namespace. | Done: workspace-scoped capsule cache namespace and invalidation are in place. |
| Benchmark | Local char/4 token estimate is lightweight. | Add optional tokenizer backend later; keep current estimate as dependency-free baseline. |
| Retrieval | Python/JS/TS indexing works with AST/regex fallback and FTS/LIKE search. | P1: Tree-sitter query patterns, BM25 weighting, import/call edges, route/test/source links. |
| Local docs safety | Secrets are redacted and external Context7 guard is strict. | P1: prompt-injection scanner for local docs and public-doc results before capsule inclusion. |
| Done P0.5 | Adapter status | `ctx install status` verifies files/endpoints, and `ctx client-check` now includes per-client manual verification checklist outputs. | Keep extending checklists when client UX changes. |
| Client status | `ctx client-check` reports adapter status, CLI availability, manual checks, and safe optional local probes. | Add Codex non-interactive MCP status probe when a stable CLI command is confirmed; keep tracking Gemini's post-list Windows libuv assertion. |

## External Comparison Notes

- Docker MCP Gateway is much broader: lifecycle management, credentials, access control, restricted containers, logging, and tracing. `ctx-engine` should not become a downstream gateway in P0, but it should borrow health/status vocabulary and container hardening ideas.
- Repomix is stronger at pack/report UX: Secretlint by default, gitignore-aware output, binary exclusion, token counts, and review-before-sharing patterns. `ctx-engine` should adopt local-only token tree and secret-check UX later without default whole-repo packing.
- localmem and mnemo-cortex show stronger multi-agent memory lifecycle patterns (namespaces, synthesis, tiered memory) that can be borrowed without importing their full tool surfaces.
- code-review-graph and graphify reinforce two roadmap items: incremental blast-radius retrieval and explicit confidence labels for extracted/inferred context.
- ast-grep is a strong candidate for optional structural search precision in P1/P2, while keeping rewrite operations outside ctx-engine tools.
- Serena is ahead on LSP-backed semantic retrieval and symbolic editing. That is valuable for P2, but its editing/shell surface is intentionally outside `ctx-engine` P0.
- CodeGraphContext is ahead on setup wizard, client breadth, graph database modes, live watching, and `.cgcignore`. Useful references: client setup UX and graph query ergonomics. Keep graph DB and watch mode out of P0.
- 2026 MCP security research and community reports have shifted the risk center from "can the server run commands?" to "can tool descriptions, hidden Unicode, indirect docs, or external tool outputs steer the agent?" This supports a P1 MCP/tool-description lint and prompt-injection scanner.

## Updated Roadmap

P0.5 next:

- Done: update protocol reporting to MCP `2025-11-25` while preserving older header compatibility.
- Done: tighten HTTP Origin/Host parsing and GET `/mcp` behavior.
- Done: add optional MCP Inspector smoke command (`ctx inspector-smoke`).
- Done: add `ctx mcp-lint` for tool metadata and schema quality checks.
- Done: add `ctx client-check` for adapter and safe local client verification.
- Done: align `tools/call` validation failures with tool execution errors (`isError=true`) for model-correctable inputs.
- Done: add `ctx doctor --strict` for strict health/warning exit behavior in local and CI checks.
- Done: make capsule cache invalidation workspace-scoped instead of clearing all workspace capsules.
- Done: add Docker non-root user, loopback-only compose port publishing, compose healthcheck, `.dockerignore`, and Docker runtime smoke.
- Done: add GitHub Actions CI quality gate for Python 3.12 tests, semantic quality gate, and Docker smoke.

P1:

- Local docs prompt-injection scanner.
- Context7 egress report and version detection.
- Tree-sitter query extraction plus better BM25/ranking.
- Repomix-like local pack summary with secret-check and token tree.
- Blast-radius query primitive for minimal review set selection.
- Confidence labels in context output (`extracted`, `inferred`, `ambiguous`).

P2:

- LSP/SCIP/graph backend experiments. LSP/SCIP/Kuzu opt-in paths exist; keep hardening real-runtime smokes.
- Live file watching.
- Multi-project manager.
- External Hindsight adapter.
- Dashboard/policy engine/verified semantic cache.
- Federated signed-delta memory experiment branch (inspired by HoloCortex/localmem patterns).

## Sources Checked

- MCP latest changelog: https://modelcontextprotocol.io/specification/2025-11-25/changelog
- MCP Streamable HTTP transport: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- MCP security best practices: https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
- MCP Inspector: https://modelcontextprotocol.io/docs/tools/inspector
- Codex MCP: https://developers.openai.com/codex/mcp
- Codex AGENTS.md: https://developers.openai.com/codex/guides/agents-md
- Codex hooks: https://developers.openai.com/codex/hooks
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- Claude Code settings: https://code.claude.com/docs/en/settings
- Gemini CLI MCP docs: https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md
- Docker MCP Gateway docs: https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/
- Repomix security docs: https://repomix.com/guide/security
- Serena MCP registry: https://github.com/mcp/oraios/serena
- CodeGraphContext GitHub: https://github.com/CodeGraphContext/CodeGraphContext
- MCP tool description smells paper: https://arxiv.org/abs/2602.14878
- AI-assisted development prompt-injection paper: https://arxiv.org/abs/2603.21642
- localmem: https://github.com/jordanaftermidnight/localmem
- mnemo-cortex: https://github.com/GuyMannDude/mnemo-cortex
- HoloCortex: https://github.com/Arkay92/HoloCortex
- graphify: https://github.com/safishamsi/graphify
- code-review-graph: https://github.com/tirth8205/code-review-graph
- ast-grep: https://github.com/ast-grep/ast-grep
