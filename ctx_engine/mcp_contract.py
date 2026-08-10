from __future__ import annotations

import json
from typing import Any
import urllib.request

from .config import DEFAULT_ENDPOINT, SUPPORTED_MODES
from .server import MCPGateway, PROTOCOL_VERSION

REQUIRED_TOOLS = {
    "workspace_register",
    "workspace_list",
    "index_repository",
    "search_symbols",
    "get_file_skeleton",
    "get_symbol_context",
    "get_symbol_references",
    "get_change_impact",
    "get_context_capsule",
    "resolve_docs_context",
    "write_session_memory",
    "read_session_memory",
    "get_action_ledger",
    "get_doctor_status",
}

BANNED_TOOL_TERMS = (
    "apply_patch",
    "command",
    "delete",
    "exec",
    "replace",
    "run_shell",
    "shell",
    "terminal",
    "write_file",
)


def check_gateway_contract(mode: str = "safe") -> dict[str, Any]:
    selected_mode = mode if mode in SUPPORTED_MODES else "safe"
    gateway = MCPGateway(selected_mode)
    result = _check_contract(lambda payload: gateway.handle_jsonrpc(payload), transport="in-process")
    result["mode"] = selected_mode
    return result


def check_http_gateway_contract(endpoint: str = DEFAULT_ENDPOINT, timeout: float = 5.0) -> dict[str, Any]:
    def call(payload: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "MCP-Protocol-Version": PROTOCOL_VERSION,
                "X-Client-Id": "mcp-check",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None

    result = _check_contract(call, transport="http")
    result["endpoint"] = endpoint
    result["timeout_seconds"] = timeout
    return result


def _check_contract(call: Any, transport: str) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    errors: list[str] = []

    def mark(name: str, passed: bool, error: str | None = None) -> None:
        checks[name] = passed
        if not passed and error:
            errors.append(error)

    def invoke(name: str, payload: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None]:
        try:
            return call(payload)
        except Exception as exc:
            mark(name, False, f"{name} request failed: {type(exc).__name__}: {exc}")
            return None, None

    status, initialized = invoke(
        "initialize",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION},
        },
    )
    init_result = (initialized or {}).get("result", {})
    if status is not None:
        mark(
            "initialize",
            status == 200 and init_result.get("serverInfo", {}).get("name") == "ctx-engine",
            "initialize did not return ctx-engine serverInfo",
        )

    status, listed = invoke("tools_list", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = (listed or {}).get("result", {}).get("tools", [])
    tool_names = sorted(str(tool.get("name")) for tool in tools if tool.get("name"))
    if status is not None:
        mark("tools_list", status == 200 and bool(tool_names), "tools/list returned no tools")

    missing = sorted(REQUIRED_TOOLS - set(tool_names))
    mark("required_tools_present", not missing, f"missing required tools: {', '.join(missing)}")

    banned = sorted(name for name in tool_names if any(term in name.lower() for term in BANNED_TOOL_TERMS))
    mark("no_shell_or_write_tools", not banned, f"banned tool names present: {', '.join(banned)}")

    schemas_valid = all(
        isinstance(tool.get("inputSchema"), dict)
        and tool["inputSchema"].get("type") == "object"
        and tool["inputSchema"].get("additionalProperties") is False
        for tool in tools
    )
    mark("json_schema_shape", schemas_valid, "one or more tools are missing strict object inputSchema")

    status, ping = invoke("ping", {"jsonrpc": "2.0", "id": 3, "method": "ping"})
    if status is not None:
        mark("ping", status == 200 and (ping or {}).get("result") == {}, "ping did not return an empty result")

    status, called = invoke(
        "tools_call_content_shape",
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "workspace_list", "arguments": {}},
        },
    )
    call_result = (called or {}).get("result", {})
    content = call_result.get("content", [])
    if status is not None:
        mark(
            "tools_call_content_shape",
            status == 200
            and call_result.get("isError") is False
            and isinstance(content, list)
            and bool(content)
            and content[0].get("type") == "text",
            "tools/call did not return MCP text content",
        )

    passed = all(checks.values())
    return {
        "status": "pass" if passed else "fail",
        "transport": transport,
        "protocol_version": PROTOCOL_VERSION,
        "checks": checks,
        "tool_count": len(tool_names),
        "tool_names": tool_names,
        "errors": errors,
    }
