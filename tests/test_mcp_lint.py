from __future__ import annotations

from ctx_engine.mcp_registry import compare_tools_to_registry, load_tool_registry
from ctx_engine.mcp_lint import lint_gateway_tools
from ctx_engine.server import ToolRegistry


def test_mcp_lint_passes_for_safe_gateway():
    result = lint_gateway_tools()
    assert result["status"] == "pass"
    assert result["tool_count"] >= 10
    assert not result["errors"]
    assert result["registry"]["status"] == "pass"


def test_mcp_registry_accepts_current_gateway_descriptors():
    result = compare_tools_to_registry(ToolRegistry().schemas())
    assert result["status"] == "pass"
    assert not result["errors"]


def test_mcp_registry_fails_on_descriptor_drift():
    tools = ToolRegistry().schemas()
    tools[0] = {**tools[0], "description": "changed descriptor"}

    result = compare_tools_to_registry(tools)

    assert result["status"] == "fail"
    assert any("description_hash drift" in error for error in result["errors"])


def test_mcp_registry_fails_on_unknown_tool():
    tools = ToolRegistry().schemas()
    tools.append(
        {
            "name": "unknown_context_tool",
            "description": "Unknown tool that should not pass registry allowlist.",
            "inputSchema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        }
    )

    result = compare_tools_to_registry(tools)

    assert result["status"] == "fail"
    assert any("not present in MCP registry" in error for error in result["errors"])


def test_mcp_registry_file_contains_current_tool_count():
    registry = load_tool_registry()
    assert len(registry["tools"]) == len(ToolRegistry().schemas())
