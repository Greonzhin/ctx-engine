from __future__ import annotations

from ctx_engine.mcp_lint import lint_gateway_tools


def test_mcp_lint_passes_for_safe_gateway():
    result = lint_gateway_tools()
    assert result["status"] in {"pass", "warn"}
    assert result["tool_count"] >= 10
    assert not result["errors"]
