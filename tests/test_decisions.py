from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.decisions import decision_report


def test_decision_report_extracts_nodes_and_edges(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "adr.md").write_text(
        """# Architecture Decisions

## Decision: MCP safety

- Do not expose shell or write tools through MCP.
- Done: Docker runtime uses a non-root user.

## P2 candidates

- Optional KuzuDB backend remains behind CTX_ENGINE_GRAPH_BACKEND.
""",
        encoding="utf-8",
    )

    result = decision_report(tmp_path, limit=10)

    assert result["status"] == "ok"
    assert result["documents_scanned"] == 1
    assert result["decision_count"] >= 3
    assert result["summary"]["by_status"]["guardrail"] >= 1
    assert result["summary"]["by_status"]["implemented"] >= 1
    assert any(edge["relation"] == "same_document_next" for edge in result["edges"])


def test_decision_report_warns_without_docs(tmp_path):
    result = decision_report(tmp_path)

    assert result["status"] == "warn"
    assert result["decision_count"] == 0
    assert "no local documentation files found" in result["warnings"]


def test_decision_report_skips_runtime_cache_docs(tmp_path):
    cache = tmp_path / ".pytest_cache"
    docs = tmp_path / "docs"
    cache.mkdir()
    docs.mkdir()
    (cache / "README.md").write_text("- Do not commit this cache.\n", encoding="utf-8")
    (docs / "adr.md").write_text("- Decision: keep local docs only.\n", encoding="utf-8")

    result = decision_report(tmp_path)

    assert result["decision_count"] == 1
    assert result["decisions"][0]["path"] == "docs/adr.md"


def test_decisions_cli(tmp_path, capsys):
    (tmp_path / "README.md").write_text(
        """# Demo

- Decision: keep SQLite as the default backend.
""",
        encoding="utf-8",
    )

    assert main(["decisions", "report", str(tmp_path), "--strict"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["decisions"][0]["category"] == "memory"
