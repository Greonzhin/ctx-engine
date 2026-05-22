from __future__ import annotations

import json

from ctx_engine.cli import main


def test_cli_init_index_and_install(tmp_path, fixture_root, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / ".ctx-engine" / "config.yaml").exists()
    assert main(["index", str(fixture_root / "python_app")]) == 0
    assert main(["capsule", "where is auth handled?"]) == 0
    assert main(["install", "codex"]) == 0
    assert (tmp_path / "AGENTS.md").exists()
    capsys.readouterr()

    assert main(["install", "status", str(tmp_path), "--adapter", "codex"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["all_installed"] is True
    assert status["clients"]["codex"]["endpoint_matches_rules"] is True

    assert main(["client-check", str(tmp_path), "--adapter", "codex"]) == 0
    client_check = json.loads(capsys.readouterr().out)
    assert client_check["status"] == "ok"
    assert client_check["clients"]["codex"]["adapter"]["installed"] is True

    assert main(["mcp-check"]) == 0
    contract = json.loads(capsys.readouterr().out)
    assert contract["status"] == "pass"

    assert main(["mcp-lint"]) == 0
    lint = json.loads(capsys.readouterr().out)
    assert lint["status"] in {"pass", "warn"}
    assert not lint["errors"]

    assert main(["inspector-smoke"]) == 0
    inspector = json.loads(capsys.readouterr().out)
    assert inspector["status"] in {"ready", "unavailable"}

    assert main(["benchmark", "authenticate request", str(fixture_root / "python_app"), "--token-budget", "1200"]) == 0
    benchmark = json.loads(capsys.readouterr().out)
    assert benchmark["status"] == "ok"
    assert benchmark["baseline"]["total_tokens"] > 0

    assert main(["docs-scan"]) == 0
    docs_scan = json.loads(capsys.readouterr().out)
    assert docs_scan["status"] == "ok"

    assert main(["pack-summary", "authenticate request"]) == 0
    pack = json.loads(capsys.readouterr().out)
    assert pack["status"] == "ok"
    assert "selected_tokens_total" in pack
    assert "omitted_tokens_total" in pack

    assert main(["blast-radius", "authenticate request"]) == 0
    blast = json.loads(capsys.readouterr().out)
    assert blast["status"] == "ok"
    assert "related_files" in blast

    assert main(["semantic-refs", "authenticate_request"]) == 0
    refs = json.loads(capsys.readouterr().out)
    assert refs["status"] == "ok"
    assert "references" in refs

    assert main(["semantic-impact", "authenticate request", "--include-tests"]) == 0
    impact = json.loads(capsys.readouterr().out)
    assert impact["status"] == "ok"
    assert "impacted_files" in impact

    assert main(["conventions"]) == 0
    conventions = json.loads(capsys.readouterr().out)
    assert conventions["status"] == "ok"
    assert "languages" in conventions["summary"]

    assert main(["egress-report", "--provider", "context7"]) == 0
    egress = json.loads(capsys.readouterr().out)
    assert egress["status"] == "ok"
    assert "by_status" in egress["summary"]
    assert "p50_latency_ms" in egress["summary"]
    assert "p95_latency_ms" in egress["summary"]
    assert "cache_hit_rate" in egress["summary"]

    assert main(["hooks", "plan", "codex"]) == 0
    hooks = json.loads(capsys.readouterr().out)
    assert hooks["status"] == "ok"
    assert hooks["clients"][0]["client_id"] == "codex"

    assert main(["feedback", "report", "--limit", "5"]) == 0
    feedback = json.loads(capsys.readouterr().out)
    assert feedback["status"] == "ok"

    assert main(["memory", "report", "--limit", "5"]) == 0
    memory = json.loads(capsys.readouterr().out)
    assert memory["status"] == "ok"

    assert main(["skill-pack", "list"]) == 0
    skill_packs = json.loads(capsys.readouterr().out)
    assert skill_packs["status"] == "ok"

    assert main(["cache", "verify"]) == 0
    cache = json.loads(capsys.readouterr().out)
    assert cache["status"] == "ok"

    assert main(["workspace", "list"]) == 0
    workspace = json.loads(capsys.readouterr().out)
    assert workspace["status"] == "ok"
    assert workspace["workspace_count"] >= 1

    assert main(["policy", "check", str(tmp_path)]) == 0
    policy = json.loads(capsys.readouterr().out)
    assert policy["status"] in {"pass", "fail"}
    assert "checks" in policy

    assert main(["retrieval-benchmark", str(fixture_root / "python_app"), "--top-k", "3"]) == 0
    retrieval = json.loads(capsys.readouterr().out)
    assert retrieval["status"] == "ok"
    assert retrieval["cases_total"] >= 1


def test_cli_doctor_strict_pass(monkeypatch, capsys):
    monkeypatch.setattr("ctx_engine.cli.doctor_status", lambda _path: {"status": "healthy", "warnings": []})
    assert main(["doctor", "--strict"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "healthy"


def test_cli_doctor_strict_fails_on_warning(monkeypatch, capsys):
    monkeypatch.setattr("ctx_engine.cli.doctor_status", lambda _path: {"status": "healthy", "warnings": ["warn"]})
    assert main(["doctor", "--strict"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["warnings"]


def test_cli_doctor_strict_fails_on_unhealthy(monkeypatch, capsys):
    monkeypatch.setattr("ctx_engine.cli.doctor_status", lambda _path: {"status": "unhealthy", "warnings": []})
    assert main(["doctor", "--strict"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "unhealthy"
