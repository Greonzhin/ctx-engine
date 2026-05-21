from __future__ import annotations

from pathlib import Path


def test_other_repos_research_doc_is_integrated():
    root = Path(__file__).resolve().parents[1]
    doc = root / "docs" / "research" / "other-repos-and-adoptables.md"
    scan_doc = root / "docs" / "research" / "context7-project-scan.md"
    expanded_doc = root / "docs" / "research" / "expanded-sources-and-untested-followup.md"
    gap_doc = root / "docs" / "research" / "current-gap-analysis-2026-05-16.md"
    readme = root / "README.md"
    assert doc.exists()
    assert scan_doc.exists()
    assert expanded_doc.exists()
    assert gap_doc.exists()
    text = doc.read_text(encoding="utf-8")
    scan_text = scan_doc.read_text(encoding="utf-8")
    expanded_text = expanded_doc.read_text(encoding="utf-8")
    gap_text = gap_doc.read_text(encoding="utf-8")
    assert "Docker MCP Gateway" in text
    assert "Serena" in text
    assert "Repomix" in text
    assert "Context7" in text
    assert "Immediate P0.5 Backlog" in text
    assert "Do not expose shell tools through ctx-engine." in text
    assert "query-docs" in scan_text
    assert "httpUrl" in scan_text
    assert "Current Tested Baseline" in expanded_text
    assert "Docker build/run" in expanded_text
    assert "MCP Inspector" in expanded_text
    assert "Real Codex MCP connection" in expanded_text
    assert "Keep-Out Rules Confirmed" in expanded_text
    assert "MCP protocol drift" in gap_text
    assert "DNS rebinding hardening" in gap_text
    assert "tool descriptions" in gap_text
    assert "2025-11-25" in gap_text
    readme_text = readme.read_text(encoding="utf-8")
    assert "Other Repositories And Adoptable Ideas" in readme_text
    assert "Context7 Project Scan" in readme_text
    assert "Expanded Sources And Untested Follow-Up" in readme_text
    assert "Current Gap Analysis" in readme_text
