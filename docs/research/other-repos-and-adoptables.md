# Other Repositories And Adoptable Ideas

Date: 2026-05-16

This note tracks adjacent projects, what ctx-engine can learn from them, and which ideas should stay out of P0. It is intentionally product-facing: every entry has an adoption decision.

## Decision Frame

ctx-engine is not trying to become a general MCP gateway catalog, an IDE refactoring server, or a full repository packer. The durable product shape remains:

- one local MCP endpoint for coding agents
- read-only repo context by default
- provenance-rich context capsules
- Codex / Claude / Gemini adapter generation
- private code stays local

Adopt ideas only when they strengthen that shape.

## Source Matrix

| Project | What It Does Well | Adoptable For ctx-engine | Timing | Boundary |
|---|---|---|---|---|
| Docker MCP Gateway | Containerized MCP server lifecycle, profiles, catalogs, tool filtering, secrets, OAuth, tracing. | Client/profile status checks, tool allowlist vocabulary, Docker isolation docs, gateway health UX. | P0.5/P1 | Do not become a downstream server catalog in P0. |
| IBM ContextForge | Enterprise gateway, registry, protocol flexibility, federation, auth, SSRF controls, admin features. | Security checklist language, SSRF/egress posture, future registry/descriptor thinking. | P1/P2 | Do not add enterprise federation/dashboard now. |
| Microsoft MCP Gateway | Kubernetes-oriented reverse proxy, session-aware routing, authorization lifecycle. | Session model notes for future remote deployments. | P2 | Not relevant to local P0. |
| Vexp | Local context capsules, cross-repo graph, git-native manifest, token-reduction benchmark narrative. | Capsule quality metrics, manifest/hash rebuild idea, cross-repo roadmap, benchmark command. | P0.5/P1/P2 | Do not copy claims without our own benchmarks. |
| Serena | LSP/JetBrains-backed symbolic retrieval and editing. | Future LSP-backed symbol references and call/reference queries. | P2 | No LSP/editing tools in P0. |
| Repomix | Whole-repo packing, gitignore support, token counts, Tree-sitter compression, Secretlint guard. | `ctx capsule --pack-summary` style fallback, token report, ignore/secret UX ideas. | P1 | Do not upload or pack private repos by default. |
| Context7 | Public, version-aware library docs via MCP. | Keep as guarded public docs provider; add better version detection and cache metadata. | P0.5 | Never send private code/docs/prompts. |
| Hindsight | Structured long-term memory, retain/recall/reflect/verify/supersede semantics. | Keep built-in SQLite memory API; improve verification/conflict lifecycle. | P0.5/P1 | No external Hindsight service in P0. |
| localmem | Local-first multi-agent memory MCP with hybrid retrieval, behavioral graph, temporal triples, wake layers, lifecycle tiers. | Memory lifecycle tiers and namespace model inspiration for built-in memory. | P1/P2 | Do not import broad write-heavy tool surface directly. |
| mnemo-cortex | Session ingestion/watcher model and cross-agent synthesis workflow. | Optional session-ingestion adapter and synthesis summary patterns. | P2 | Keep default deployment dependency-free and format-agnostic. |
| HoloCortex | Federated P2P knowledge graph, signed deltas, trust-weighted contradiction resolution. | Provenance/trust weighting ideas for conflict handling. | P2 | No P2P federation in local-only core path. |
| graphify | Multimodal graph build + update/watch + inferred/extracted labels. | Label certainty in context artifacts and future watch-mode ergonomics. | P1/P2 | No mandatory external model dependency in core flow. |
| code-review-graph | Incremental graph updates and blast-radius review context. | Add blast-radius query primitive and benchmark discipline. | P1/P2 | Do not auto-modify external client configs without explicit command. |
| ast-grep | Structural AST search/lint/rewrite CLI. | Optional structural-search adapter for precise matching and rule validation. | P1/P2 | Keep rewrite/codemod operations out of ctx-engine tools. |
| RTK | Token-saving command-output compression, fast binary, measurable claims. | Add benchmark discipline and optional terminal-output compression later. | P1 | Internal RTK remains retrieval/token toolkit, not external dependency. |
| codebase-memory / codebase-context class of tools | Tree-sitter graph, convention mapping, hybrid search. | Add convention extraction, route/test/source links, BM25 scoring. | P1 | Keep P0 index simple and deterministic. |

## Immediate P0.5 Backlog

These are safe to add next without changing the P0 promise.

1. MCP conformance test
   - Add a local test that performs `initialize`, `tools/list`, and `tools/call`.
   - Add a note for using the official MCP Inspector manually.
   - Keep the custom stdlib server only if conformance remains simple; otherwise evaluate official Python SDK/FastMCP.

2. Adapter verification
   - Add `ctx install status`.
   - Validate generated Codex, Claude, and Gemini config files against expected HTTP fields.
   - For Gemini, prefer `httpUrl` for Streamable HTTP while preserving compatibility notes for `url`.

3. Cache and index invalidation
   - Add workspace index hash.
   - Include index version and file hash set in capsule cache keys.
   - Clear affected capsule/docs cache entries when indexed files change.

4. Benchmark command
   - Add `ctx benchmark tests/fixtures/...`.
   - Report selected files, estimated tokens, omitted files, and full-repo baseline.
   - Avoid marketing claims until repeatable numbers exist.

5. Security surface report
   - Done: add `ctx doctor --strict`.
   - Report network mode, Context7 live flag, ignored paths, secret redaction, and exposed MCP tools.
   - Confirm no shell/write tools are exposed.

## P1 Candidates

- Descriptor hash registry and tool allowlist, inspired by Docker gateway profiles and MCP security guidance.
- Prompt-injection scanner for local docs and external docs results.
- Egress report for Context7 calls.
- Better code retrieval: BM25 over symbols/docs, route extraction, source-to-test links.
- Repomix-like compact pack fallback for cold starts, local-only and redacted.
- Hook adapters where Codex/Claude/Gemini expose stable hook points.
- Blast-radius style query and minimal review set selector.
- Retrieval confidence labeling (`extracted` / `inferred` / `ambiguous`) in capsule artifacts.

## P2 Candidates

- LSP or SCIP ingestion for references, call graph, rename-safe symbol facts.
- Optional graph backend for large repos.
- Cross-repo workspace manager and git-native manifest.
- Dashboard and policy engine.
- External Hindsight adapter.
- Federated signed-delta memory experiment branch.
- Remote multi-user gateway with auth/session model.

## Things Not To Adopt

- Do not expose shell tools through ctx-engine.
- Do not expose repo write/edit tools through ctx-engine.
- Do not add downstream untrusted MCP gatewaying without descriptor hash and allowlist.
- Do not add external Hindsight as a required service.
- Do not add LSP, SCIP, KuzuDB, dashboard, policy engine, or verified semantic cache before P1/P2.
- Do not send private code, private docs, proprietary snippets, internal OpenAPI specs, secrets, or full prompts to Context7.

## Validation Checklist

Use this when converting an idea into an issue:

- Does it preserve one MCP gateway endpoint?
- Does it keep the workspace read-only by default?
- Does it improve context quality, safety, or adapter reliability?
- Can it be tested without external paid services?
- Does it avoid private-source egress?
- Is it P0.5/P1/P2 scoped clearly?

## Sources

- Docker MCP Gateway: https://github.com/docker/mcp-gateway
- Docker MCP Gateway docs: https://docs.docker.com/ai/mcp-gateway/
- IBM ContextForge: https://github.com/IBM/mcp-context-forge
- Microsoft MCP Gateway: https://github.com/microsoft/mcp-gateway
- Vexp: https://vexp.dev/
- Serena: https://github.com/oraios/serena
- Repomix: https://github.com/yamadashy/repomix
- Context7: https://github.com/upstash/context7
- RTK: https://github.com/rtk-ai/rtk
- localmem: https://github.com/jordanaftermidnight/localmem
- mnemo-cortex: https://github.com/GuyMannDude/mnemo-cortex
- HoloCortex: https://github.com/Arkay92/HoloCortex
- graphify: https://github.com/safishamsi/graphify
- code-review-graph: https://github.com/tirth8205/code-review-graph
- ast-grep: https://github.com/ast-grep/ast-grep
- MCP transports: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP security best practices: https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
- OpenAI Docs MCP: https://developers.openai.com/learn/docs-mcp
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- Gemini CLI MCP: https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md
