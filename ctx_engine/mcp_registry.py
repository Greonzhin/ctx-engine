from __future__ import annotations

import hashlib
import json
from importlib import resources
from typing import Any


REGISTRY_RESOURCE = "mcp_tool_registry.json"


def stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_tool_registry() -> dict[str, Any]:
    text = resources.files("ctx_engine").joinpath(REGISTRY_RESOURCE).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("tools"), dict):
        raise ValueError("MCP tool registry must be an object with a tools object.")
    return data


def tool_descriptor_hashes(tool: dict[str, Any]) -> dict[str, str]:
    return {
        "description_hash": stable_hash(str(tool.get("description") or "")),
        "input_schema_hash": stable_hash(tool.get("inputSchema") or {}),
    }


def compare_tools_to_registry(tools: list[dict[str, Any]], registry: dict[str, Any] | None = None) -> dict[str, Any]:
    selected_registry = registry or load_tool_registry()
    registered = selected_registry["tools"]
    errors: list[str] = []
    warnings: list[str] = []
    reports: list[dict[str, Any]] = []

    seen_names = {str(tool.get("name") or "") for tool in tools if tool.get("name")}
    for tool in tools:
        name = str(tool.get("name") or "")
        entry = registered.get(name)
        report = {"name": name, "registry": "missing", "errors": [], "warnings": []}
        if not isinstance(entry, dict):
            report["errors"].append("tool is not present in MCP registry")
            reports.append(report)
            continue
        report["registry"] = "matched"
        if entry.get("allowed") is not True:
            report["errors"].append("tool is not allowed by MCP registry")
        if not entry.get("risk"):
            report["errors"].append("tool registry entry must include risk")
        hashes = tool_descriptor_hashes(tool)
        for key in ("description_hash", "input_schema_hash"):
            if entry.get(key) != hashes[key]:
                report["errors"].append(f"{key} drift: expected {entry.get(key)}, got {hashes[key]}")
        if report["errors"] or report["warnings"]:
            reports.append(report)

    disabled_present = sorted(name for name, entry in registered.items() if isinstance(entry, dict) and entry.get("allowed") is False and name in seen_names)
    for name in disabled_present:
        errors.append(f"{name}: tool is disabled in MCP registry")

    for report in reports:
        errors.extend(f"{report['name']}: {item}" for item in report["errors"])
        warnings.extend(f"{report['name']}: {item}" for item in report["warnings"])

    return {
        "status": "pass" if not errors else "fail",
        "errors": sorted(errors),
        "warnings": sorted(warnings),
        "registered_tool_count": len(registered),
        "registry_reports": reports,
        "registry_version": selected_registry.get("version"),
    }
