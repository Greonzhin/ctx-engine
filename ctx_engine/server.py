from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import __version__
from .capsule.builder import CapsuleBuilder
from .config import DEFAULT_HOST, DEFAULT_PORT, SUPPORTED_MODES
from .doctor import doctor_status
from .providers.action_ledger import ActionLedger
from .providers.code_graph import CodeGraphProvider
from .providers.context7_docs import Context7DocsProvider
from .providers.local_docs import LocalDocsProvider
from .providers.memory import BuiltInMemoryProvider
from .workspace import get_workspace, list_workspaces, register_workspace

PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = {"2025-03-26", "2025-06-18", PROTOCOL_VERSION}
LOCAL_HTTP_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ToolExecutionError(Exception):
    pass


def _json_default(value: object) -> str:
    return str(value)


def _negotiate_protocol_version(value: object) -> str:
    requested = str(value) if value else PROTOCOL_VERSION
    return requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION


def _local_host_allowed(host_value: str | None) -> bool:
    if not host_value:
        return True
    parsed = urlparse(f"//{host_value}")
    return bool(parsed.hostname and parsed.hostname.lower() in LOCAL_HTTP_HOSTS)


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname and parsed.hostname.lower() in LOCAL_HTTP_HOSTS)


def _accept_allows_json(accept: str | None) -> bool:
    if not accept:
        return True
    lowered = accept.lower()
    return "*/*" in lowered or "application/json" in lowered


class ToolRegistry:
    def __init__(self, mode: str = "safe") -> None:
        self.mode = mode
        self.code = CodeGraphProvider()
        self.docs = Context7DocsProvider(mode=mode)
        self.memory = BuiltInMemoryProvider()
        self.ledger = ActionLedger()
        self._schemas = [
            self._schema("workspace_register", "Register a read-only workspace path.", {"path": "string"}, ["path"]),
            self._schema("workspace_list", "List registered workspaces.", {}, []),
            self._schema("index_repository", "Index an already registered workspace or explicit path.", {"workspace_id": "string", "path": "string"}, []),
            self._schema("search_symbols", "Search indexed symbols.", {"query": "string", "workspace_id": "string"}, ["query"]),
            self._schema("get_file_skeleton", "Return a file skeleton from the code graph.", {"path": "string", "workspace_id": "string"}, ["path"]),
            self._schema("get_symbol_context", "Return symbol signature and exact local snippet.", {"symbol_name": "string", "workspace_id": "string"}, ["symbol_name"]),
            self._schema("get_symbol_references", "Return semantic references for a symbol.", {"symbol_name": "string", "workspace_id": "string", "depth": "integer", "limit": "integer"}, ["symbol_name"]),
            self._schema("get_change_impact", "Return semantic blast radius and impacted files for a query.", {"query": "string", "workspace_id": "string", "depth": "integer", "limit": "integer", "include_tests": "boolean"}, ["query"]),
            self._schema("get_blast_radius", "Return a related-file blast radius around seed symbols.", {"query": "string", "workspace_id": "string", "depth": "integer", "limit": "integer"}, ["query"]),
            self._schema("get_context_capsule", "Build a provenance-rich context capsule.", {"query": "string", "token_budget": "integer", "include_docs": "boolean", "client_id": "string", "workspace_id": "string"}, ["query"]),
            self._schema("resolve_docs_context", "Resolve public docs context via Context7 guard.", {"query": "string"}, ["query"]),
            self._schema("write_session_memory", "Write advisory built-in session memory.", {"content": "string", "files": "array", "symbols": "array", "docs": "array", "workspace_id": "string", "lifecycle_tier": "string", "agent_namespace": "string"}, ["content"]),
            self._schema("read_session_memory", "Read built-in session memory.", {"query": "string", "scope": "string", "workspace_id": "string", "agent_namespace": "string"}, []),
            self._schema("apply_memory_lifecycle_policy", "Apply hot/warm/cold lifecycle policy to memories.", {"workspace_id": "string", "agent_namespace": "string", "hot_days": "integer", "warm_days": "integer"}, []),
            self._schema("get_action_ledger", "Read action ledger entries.", {"query": "string"}, []),
            self._schema("get_doctor_status", "Return local ctx-engine doctor status.", {}, []),
        ]
        self._schema_map = {tool["name"]: tool for tool in self._schemas}

    def schemas(self) -> list[dict[str, object]]:
        return list(self._schemas)

    @staticmethod
    def _schema(name: str, description: str, properties: dict[str, str], required: list[str]) -> dict[str, object]:
        return {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": {key: {"type": value} for key, value in properties.items()},
                "required": required,
                "additionalProperties": False,
            },
        }

    @staticmethod
    def _matches_type(value: object, expected: str) -> bool:
        if expected == "string":
            return isinstance(value, str)
        if expected == "integer":
            return type(value) is int
        if expected == "boolean":
            return isinstance(value, bool)
        if expected == "array":
            return isinstance(value, list)
        if expected == "object":
            return isinstance(value, dict)
        return True

    def validate_call(self, name: str, args: object) -> dict[str, Any]:
        tool = self._schema_map.get(name)
        if tool is None:
            raise ToolExecutionError(f"unknown tool: {name}")
        if args is None:
            return {}
        if not isinstance(args, dict):
            raise ToolExecutionError("tool arguments must be an object")

        input_schema = tool["inputSchema"]
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])
        errors: list[str] = []

        missing = [key for key in required if key not in args]
        if missing:
            errors.append(f"missing required fields: {', '.join(sorted(missing))}")

        if input_schema.get("additionalProperties") is False:
            unknown = [key for key in args if key not in properties]
            if unknown:
                errors.append(f"unknown fields: {', '.join(sorted(unknown))}")

        for key, value in args.items():
            prop = properties.get(key)
            if not isinstance(prop, dict):
                continue
            expected_type = prop.get("type")
            if isinstance(expected_type, str) and not self._matches_type(value, expected_type):
                errors.append(f"field '{key}' must be {expected_type}")

        if errors:
            raise ToolExecutionError("; ".join(errors))
        return dict(args)

    def call(self, name: str, args: dict[str, Any], client_id: str = "generic") -> Any:
        args = self.validate_call(name, args)
        workspace_id = args.get("workspace_id")
        if name == "workspace_register":
            return register_workspace(args["path"])
        if name == "workspace_list":
            return list_workspaces()
        if name == "index_repository":
            path = args.get("path")
            if not path and workspace_id:
                workspace = get_workspace(str(workspace_id))
                path = workspace["root_path"] if workspace else None
            if not path:
                workspace = get_workspace()
                path = workspace["root_path"] if workspace else "."
            result = self.code.index_repository(str(path))
            local_docs = LocalDocsProvider().index(result["root_path"], str(result["workspace_id"]))
            result["local_docs"] = local_docs
            self.ledger.record("index", f"indexed {path}", result, client_id=client_id, workspace_id=str(result["workspace_id"]))
            return result
        if name == "search_symbols":
            return self.code.search_symbols(str(args["query"]), workspace_id=workspace_id)
        if name == "get_file_skeleton":
            return self.code.get_file_skeleton(str(args["path"]), workspace_id=workspace_id)
        if name == "get_symbol_context":
            return self.code.get_symbol_context(str(args["symbol_name"]), workspace_id=workspace_id)
        if name == "get_symbol_references":
            return self.code.get_symbol_references(
                str(args["symbol_name"]),
                workspace_id=workspace_id,
                depth=int(args.get("depth", 1)),
                limit=int(args.get("limit", 30)),
            )
        if name == "get_change_impact":
            return self.code.get_change_impact(
                str(args["query"]),
                workspace_id=workspace_id,
                depth=int(args.get("depth", 1)),
                limit=int(args.get("limit", 30)),
                include_tests=bool(args.get("include_tests", False)),
            )
        if name == "get_blast_radius":
            return self.code.blast_radius(
                str(args["query"]),
                workspace_id=workspace_id,
                depth=int(args.get("depth", 1)),
                limit=int(args.get("limit", 30)),
            )
        if name == "get_context_capsule":
            return CapsuleBuilder(mode=self.mode).build(
                str(args["query"]),
                int(args.get("token_budget", 4000)),
                bool(args.get("include_docs", True)),
                client_id=str(args.get("client_id", client_id)),
                workspace_id=workspace_id,
            )
        if name == "resolve_docs_context":
            resolved = self.docs.resolve(str(args["query"]))
            if resolved.get("library_id"):
                resolved["context"] = self.docs.query(str(resolved["library_id"]), str(args["query"]))
            return resolved
        if name == "write_session_memory":
            return self.memory.retain(
                str(args["content"]),
                workspace_id=workspace_id,
                files=list(args.get("files") or []),
                symbols=list(args.get("symbols") or []),
                docs=list(args.get("docs") or []),
                lifecycle_tier=str(args.get("lifecycle_tier") or "warm"),
                agent_namespace=str(args.get("agent_namespace") or "default"),
            )
        if name == "read_session_memory":
            return self.memory.recall(
                str(args.get("query", "")),
                workspace_id=workspace_id,
                scope=str(args.get("scope", "project")),
                agent_namespace=str(args.get("agent_namespace", "default")),
            )
        if name == "apply_memory_lifecycle_policy":
            return self.memory.apply_lifecycle_policy(
                workspace_id=workspace_id,
                agent_namespace=str(args.get("agent_namespace", "default")),
                hot_days=int(args["hot_days"]) if "hot_days" in args and args["hot_days"] is not None else None,
                warm_days=int(args["warm_days"]) if "warm_days" in args and args["warm_days"] is not None else None,
            )
        if name == "get_action_ledger":
            return self.ledger.tail(query=str(args.get("query", "")))
        if name == "get_doctor_status":
            return doctor_status()
        raise ToolExecutionError(f"unknown tool: {name}")


class MCPGateway:
    def __init__(self, mode: str = "safe") -> None:
        self.mode = mode if mode in SUPPORTED_MODES else "safe"
        self.registry = ToolRegistry(mode=self.mode)

    def handle_jsonrpc(self, payload: dict[str, Any], client_id: str = "generic") -> tuple[int, dict[str, Any] | None]:
        method = payload.get("method")
        request_id = payload.get("id")
        try:
            if method == "initialize":
                negotiated_version = _negotiate_protocol_version(
                    payload.get("params", {}).get("protocolVersion")
                )
                return 200, {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": negotiated_version,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "ctx-engine", "version": __version__},
                        "instructions": "Use ctx-engine for read-only repository context. No shell or write tools are exposed.",
                    },
                }
            if method == "notifications/initialized":
                return 202, None
            if method == "ping":
                return 200, {"jsonrpc": "2.0", "id": request_id, "result": {}}
            if method == "tools/list":
                return 200, {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.registry.schemas()}}
            if method == "tools/call":
                params = payload.get("params") or {}
                name = params.get("name")
                args = params.get("arguments")
                try:
                    result = self.registry.call(str(name), args, client_id=client_id)
                except ToolExecutionError as exc:
                    return 200, {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": str(exc),
                                }
                            ],
                            "isError": True,
                        },
                    }
                return 200, {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, ensure_ascii=False, sort_keys=True, default=_json_default),
                            }
                        ],
                        "isError": False,
                    },
                }
            if request_id is None:
                return 202, None
            return self._error(request_id, -32601, f"Method not found: {method}")
        except Exception as exc:
            return self._error(request_id, -32000, str(exc), type(exc).__name__)

    @staticmethod
    def _error(request_id: object, code: int, message: str, data: object | None = None) -> tuple[int, dict[str, Any]]:
        return 200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message, "data": data}}


def make_handler(mode: str) -> type[BaseHTTPRequestHandler]:
    gateway = MCPGateway(mode)

    class Handler(BaseHTTPRequestHandler):
        server_version = f"ctx-engine/{__version__}"

        def _write_json(self, status: int, value: object | None) -> None:
            self.send_response(status)
            self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
            self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type, MCP-Protocol-Version, X-Client-Id")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Vary", "Origin")
            if value is None:
                self.end_headers()
                return
            body = json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._write_json(204, None)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._write_json(200, {"status": "ok", "mode": mode, "version": __version__})
            elif self.path == "/mcp":
                self._write_json(405, {"error": "sse stream is not supported; use POST JSON-RPC on this endpoint"})
            else:
                self._write_json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/mcp":
                self._write_json(404, {"error": "not found"})
                return
            if not _origin_allowed(self.headers.get("Origin")):
                self._write_json(403, {"error": "forbidden origin"})
                return
            if not _local_host_allowed(self.headers.get("Host")):
                self._write_json(403, {"error": "forbidden host"})
                return
            if not _accept_allows_json(self.headers.get("Accept")):
                self._write_json(406, {"error": "client must accept application/json"})
                return
            protocol_version = self.headers.get("MCP-Protocol-Version")
            if protocol_version and protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
                self._write_json(400, {"error": "unsupported MCP protocol version", "supported": sorted(SUPPORTED_PROTOCOL_VERSIONS)})
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._write_json(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                return
            status, response = gateway.handle_jsonrpc(payload, client_id=self.headers.get("X-Client-Id", "generic"))
            self._write_json(status, response)

        def log_message(self, format: str, *args: object) -> None:
            if mode in {"dev", "audit"}:
                super().log_message(format, *args)

    return Handler


def make_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, mode: str = "safe") -> ThreadingHTTPServer:
    os.environ["CTX_ENGINE_MODE"] = mode
    return ThreadingHTTPServer((host, port), make_handler(mode))


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, mode: str = "safe") -> None:
    server = make_server(host, port, mode)
    print(f"ctx-engine MCP gateway listening on http://{host}:{server.server_port}/mcp mode={mode}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
