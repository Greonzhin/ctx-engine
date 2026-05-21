from __future__ import annotations

import re
from typing import Any

from .config import SUPPORTED_MODES
from .mcp_registry import compare_tools_to_registry
from .server import MCPGateway

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
MIN_DESCRIPTION_LEN = 20
BANNED_TERMS = (
    "apply_patch",
    "delete",
    "exec",
    "run shell",
    "shell",
    "terminal",
    "write file",
)
INVISIBLE_CHARS = {"\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"}


def _has_invisible(text: str) -> bool:
    return any(ch in text for ch in INVISIBLE_CHARS)


def lint_gateway_tools(mode: str = "safe") -> dict[str, Any]:
    selected_mode = mode if mode in SUPPORTED_MODES else "safe"
    gateway = MCPGateway(selected_mode)
    status, response = gateway.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    if status != 200 or not response or "result" not in response:
        return {
            "status": "fail",
            "mode": selected_mode,
            "errors": ["tools/list did not return a valid MCP response"],
            "warnings": [],
            "tool_count": 0,
            "tools": [],
        }

    tools = list((response.get("result") or {}).get("tools") or [])
    errors: list[str] = []
    warnings: list[str] = []
    tool_reports: list[dict[str, Any]] = []

    for tool in tools:
        name = str(tool.get("name") or "")
        description = str(tool.get("description") or "")
        schema = tool.get("inputSchema")
        report = {"name": name, "errors": [], "warnings": []}

        if not NAME_RE.match(name):
            report["errors"].append("tool name should match ^[a-z][a-z0-9_]*$")
        if _has_invisible(name):
            report["errors"].append("tool name contains invisible unicode characters")
        if not description or len(description.strip()) < MIN_DESCRIPTION_LEN:
            report["warnings"].append("tool description is too short")
        if _has_invisible(description):
            report["errors"].append("tool description contains invisible unicode characters")
        lowered = f"{name}\n{description}".lower()
        if any(term in lowered for term in BANNED_TERMS):
            report["errors"].append("tool metadata contains banned shell/write term")

        if not isinstance(schema, dict):
            report["errors"].append("inputSchema must be an object")
        else:
            if schema.get("type") != "object":
                report["errors"].append("inputSchema.type must be object")
            if schema.get("additionalProperties") is not False:
                report["errors"].append("inputSchema.additionalProperties must be false")
            properties = schema.get("properties")
            required = schema.get("required")
            if not isinstance(properties, dict):
                report["errors"].append("inputSchema.properties must be an object")
            if not isinstance(required, list):
                report["errors"].append("inputSchema.required must be an array")
            if isinstance(properties, dict) and isinstance(required, list):
                unknown_required = [item for item in required if item not in properties]
                if unknown_required:
                    report["errors"].append(f"required keys missing in properties: {', '.join(map(str, unknown_required))}")

        if report["errors"] or report["warnings"]:
            tool_reports.append(report)
        errors.extend(f"{name}: {item}" for item in report["errors"])
        warnings.extend(f"{name}: {item}" for item in report["warnings"])

    registry_result = compare_tools_to_registry(tools)
    errors.extend(registry_result["errors"])
    warnings.extend(registry_result["warnings"])

    overall = "pass"
    if errors:
        overall = "fail"
    elif warnings:
        overall = "warn"

    return {
        "status": overall,
        "mode": selected_mode,
        "errors": sorted(errors),
        "warnings": sorted(warnings),
        "tool_count": len(tools),
        "registry": {
            "status": registry_result["status"],
            "version": registry_result["registry_version"],
            "registered_tool_count": registry_result["registered_tool_count"],
            "reports": registry_result["registry_reports"],
        },
        "tools": tool_reports,
    }
