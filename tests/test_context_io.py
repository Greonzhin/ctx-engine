from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.context_io import export_context, import_context, write_context_export
from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.local_docs import LocalDocsProvider
from ctx_engine.providers.memory import BuiltInMemoryProvider


def _indexed_workspace(root):
    code = CodeGraphProvider().index_repository(root)
    LocalDocsProvider().index(root, str(code["workspace_id"]))
    return code


def test_context_export_contains_workspace_memory_and_decisions(fixture_root):
    root = fixture_root / "python_app"
    code = _indexed_workspace(root)
    BuiltInMemoryProvider().retain("Auth memory for export", workspace_id=str(code["workspace_id"]), lifecycle_tier="hot")

    result = export_context(root, workspace_id=str(code["workspace_id"]))

    assert result["status"] == "ok"
    assert result["version"] == 1
    assert result["workspace"]["id"] == code["workspace_id"]
    assert result["memories"][0]["claim"] == "Auth memory for export"
    assert "fingerprint" in result["workspace"]
    assert "decision_summary" in result


def test_context_import_is_dry_run_by_default_and_apply_writes_memory(fixture_root, tmp_path):
    root = fixture_root / "python_app"
    code = _indexed_workspace(root)
    BuiltInMemoryProvider().retain("Importable auth memory", workspace_id=str(code["workspace_id"]))
    payload = export_context(root, workspace_id=str(code["workspace_id"]))
    out = tmp_path / "ctx-export.json"
    write_context_export(payload, out)

    dry = import_context(out, workspace_id=str(code["workspace_id"]), apply=False)
    assert dry["mode"] == "dry-run"
    assert dry["memories_imported"] == 0

    applied = import_context(out, workspace_id=str(code["workspace_id"]), apply=True, agent_namespace="restore")
    assert applied["mode"] == "apply"
    assert applied["memories_imported"] == 1
    rows = BuiltInMemoryProvider().recall("Importable", workspace_id=str(code["workspace_id"]), agent_namespace="restore")
    assert rows


def test_context_cli_export_and_import_dry_run(fixture_root, tmp_path, capsys):
    root = fixture_root / "python_app"
    code = _indexed_workspace(root)
    BuiltInMemoryProvider().retain("CLI context export memory", workspace_id=str(code["workspace_id"]))
    out = tmp_path / "ctx-export.json"

    assert main(["context", "export", str(root), "--workspace-id", str(code["workspace_id"]), "--output", str(out)]) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["status"] == "ok"
    assert out.exists()

    assert main(["context", "import", str(out), "--workspace-id", str(code["workspace_id"])]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["mode"] == "dry-run"
    assert imported["imports"][0]["claim"] == "CLI context export memory"
