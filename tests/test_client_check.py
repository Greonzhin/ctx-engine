from __future__ import annotations

from ctx_engine.client_adapters import CodexAdapter
from ctx_engine.client_check import check_clients


def test_client_check_reports_adapter_status_without_running_clients(tmp_path):
    CodexAdapter().install(tmp_path)
    result = check_clients(tmp_path, adapter="codex", run=False)

    assert result["status"] == "ok"
    assert result["clients"]["codex"]["adapter"]["installed"] is True
    assert result["clients"]["codex"]["cli"]["version"] is None
    assert result["clients"]["codex"]["manual_checks"]
    assert result["clients"]["codex"]["manual_checks"][0]["name"] == "codex_mcp_ui"
    assert result["ran_client_commands"] is False


def test_client_check_reports_missing_adapter(tmp_path):
    result = check_clients(tmp_path, adapter="claude", run=False)

    assert result["status"] == "needs_attention"
    assert result["clients"]["claude"]["adapter"]["installed"] is False
    assert result["clients"]["claude"]["manual_checks"][0]["command"] == "claude mcp get ctx-engine"
    assert "claude adapter files are not installed" in result["warnings"]
