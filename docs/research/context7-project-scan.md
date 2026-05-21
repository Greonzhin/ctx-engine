# Context7 Project Scan

Date: 2026-05-21

Scope: scan the whole ctx-engine P0 project for public documentation surfaces that are safe and useful to query through Context7. No private source code, internal docs, prompts, secrets, or proprietary snippets were sent. Queries used only library names and short public-doc topics.

## Summary

The scan found three immediate changes:

1. Context7 MCP tool names are currently `resolve-library-id` and `query-docs`; the old `get-library-docs` name failed. The local Context7 client was updated accordingly.
2. Gemini CLI HTTP MCP config should use `httpUrl` for Streamable HTTP servers. The Gemini adapter now generates `httpUrl`.
3. ctx-engine should know more Context7 IDs by default: MCP Python SDK, tree-sitter-language-pack, py-tree-sitter, setuptools, Docker docs, Codex, Claude Code, Gemini CLI, Python/CPython, pytest, and Context7 itself.

## Project Surfaces

| Surface | Local Use | Context7 ID | Scan Result | Action |
|---|---|---|---|---|
| MCP Python SDK | Future conformance reference for HTTP MCP sessions/tools. | `/modelcontextprotocol/python-sdk` | Confirms Streamable HTTP client/session/list-tools patterns. | P0.5: add SDK/Inspector conformance smoke. |
| Context7 | Public docs provider integration. | `/upstash/context7` | Confirms `resolve-library-id` and `query-docs` tool names. | Done: updated live client. |
| tree-sitter-language-pack | P0 parser dependency. | `/kreuzberg-dev/tree-sitter-language-pack` | Confirms `get_parser(name)` and reusable parser guidance. | Done: default resolver mapping added. |
| py-tree-sitter | Underlying parser API. | `/tree-sitter/py-tree-sitter` | Confirms parser, Query, QueryCursor, and incremental parse APIs. | P1: replace regex JS/TS extraction with query patterns. |
| pytest | Test runner and fixtures. | `/pytest-dev/pytest` | Confirms pytest config, `tmp_path`, `monkeypatch`, pyproject config. | Keep current tests; add integration tests for new P0.5 items. |
| setuptools | Build backend and package data. | `/pypa/setuptools` | Confirms `pyproject.toml`, package data, console script patterns. | Current packaging is aligned. |
| Docker docs | Dockerfile/compose runtime. | `/docker/docs` | Confirms Python slim image patterns, bind mounts, compose ports, non-root user best practice. | Done: non-root container user, loopback publish, compose healthcheck, `.dockerignore`, and Docker smoke. |
| Codex CLI | Generated adapter. | `/openai/codex` | Confirms AGENTS.md project guidance and MCP server status/reload surfaces. | P0.5: add adapter status/reload note. |
| Claude Code | Generated adapter. | `/anthropics/claude-code` | Confirms HTTP MCP server config shape and `.mcp.json` usage patterns. | Current adapter acceptable; add status validation. |
| Gemini CLI | Generated adapter. | `/google-gemini/gemini-cli` | Confirms HTTP MCP server config uses `httpUrl`. | Done: Gemini adapter changed from `url` to `httpUrl`. |
| Python/CPython | stdlib SQLite and HTTP server. | `/python/cpython` | Confirms `sqlite3.Row` row factory guidance. | Current DB connection pattern is aligned. |

## Commands Used

Representative safe scan commands:

```bash
CTX_ENGINE_CONTEXT7_LIVE=1 ctx docs query /modelcontextprotocol/python-sdk "Streamable HTTP server tools list tools call initialize Python SDK"
CTX_ENGINE_CONTEXT7_LIVE=1 ctx docs query /upstash/context7 "MCP resolve-library-id query-docs streamable HTTP"
CTX_ENGINE_CONTEXT7_LIVE=1 ctx docs query /kreuzberg-dev/tree-sitter-language-pack "get_parser supported languages Python TypeScript JavaScript parser usage"
CTX_ENGINE_CONTEXT7_LIVE=1 ctx docs query /pytest-dev/pytest "pyproject testpaths addopts fixtures tmp_path monkeypatch"
CTX_ENGINE_CONTEXT7_LIVE=1 ctx docs query /docker/docs "Dockerfile python slim volumes bind mount localhost port publish compose"
CTX_ENGINE_CONTEXT7_LIVE=1 ctx docs query /google-gemini/gemini-cli "MCP servers settings.json httpUrl GEMINI.md project configuration"
```

## Implementation Changes From Scan

- Updated `ctx_engine.integrations.context7.Context7Client` to call `query-docs`.
- Added SSE `data:` response parsing for Context7 MCP responses.
- Expanded `Context7DocsProvider` known library mappings.
- Expanded `templates/context7_libraries.yaml`.
- Updated Gemini adapter output to use `httpUrl`.
- Added tests for Context7 SSE parsing and scan-doc integration.

## Recommended Next Work

P0.5:

- Add a `ctx docs scan-project` command that reads manifests and emits this kind of report automatically.
- Add official MCP Python SDK conformance smoke in dev extras.
- Add `ctx install status` for generated adapters.
- Done: add Docker non-root user and runtime smoke.

P1:

- Add tree-sitter query patterns for Python/JS/TS symbols instead of regex fallback for JS/TS.
- Add Context7 egress report in the action ledger.
- Add version detection from `pyproject.toml`, `package.json`, and lockfiles.

Keep out of P0:

- No external Hindsight service.
- No shell/write MCP tools.
- No required/default LSP, SCIP, KuzuDB, dashboard, policy engine, or verified semantic cache in P0. LSP/SCIP/Kuzu are explicit opt-in P2 paths.
