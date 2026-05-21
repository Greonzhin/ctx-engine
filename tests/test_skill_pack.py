from __future__ import annotations

import json

from ctx_engine.cli import main
from ctx_engine.skill_pack import build_skill_pack, list_skill_packs, render_skill_pack, write_skill_pack


def test_skill_pack_list_matches_workflows():
    result = list_skill_packs()

    assert result["status"] == "ok"
    assert result["count"] == 5
    assert "ctx-fix-failing-test" in {item["name"] for item in result["skill_packs"]}
    assert all(item["auto_install"] is False for item in result["skill_packs"])


def test_skill_pack_generate_by_name_is_deterministic():
    first = build_skill_pack("security-audit")
    second = build_skill_pack("security-audit")

    assert first["status"] == "ok"
    assert first["name"] == "ctx-security-audit"
    assert first["manifest"]["source_recipe"] == "security-audit"
    assert first["manifest"]["auto_install"] is False
    assert first["files"][0]["sha256"] == second["files"][0]["sha256"]
    assert "ctx security-scan . --all" in first["files"][0]["content"]


def test_skill_pack_generate_by_query_uses_workflow_suggestion():
    result = build_skill_pack("fix failing auth test")

    assert result["source_recipe"] == "fix-failing-test"
    assert result["selected_by"] == "query"
    assert "Do not weaken assertions" in result["files"][0]["content"]


def test_skill_pack_render_and_write(tmp_path):
    pack = build_skill_pack("update-docs")
    markdown = render_skill_pack(pack, "markdown")
    written = write_skill_pack(pack, tmp_path / "skill")

    assert markdown.startswith("# ctx-update-docs")
    assert written["status"] == "ok"
    assert (tmp_path / "skill" / "SKILL.md").exists()
    manifest = json.loads((tmp_path / "skill" / "skill-pack.json").read_text(encoding="utf-8"))
    assert manifest["source_recipe"] == "update-docs"


def test_skill_pack_cli(capsys, tmp_path):
    assert main(["skill-pack", "list"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["status"] == "ok"

    assert main(["skill-pack", "generate", "security audit", "--format", "json"]) == 0
    generated = json.loads(capsys.readouterr().out)
    assert generated["name"] == "ctx-security-audit"

    assert main(["skill-pack", "generate", "prepare-pr", "--output", str(tmp_path / "out")]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["skill_pack"]["name"] == "ctx-prepare-pr"
    assert (tmp_path / "out" / "SKILL.md").exists()
