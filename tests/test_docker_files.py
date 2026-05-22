from __future__ import annotations

from pathlib import Path


def test_dockerfile_uses_non_root_runtime_user():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")

    assert "groupadd --system --gid 10001 ctx-engine" in dockerfile
    assert "useradd --system --uid 10001" in dockerfile
    assert "USER 10001:10001" in dockerfile


def test_compose_binds_gateway_to_loopback_and_non_root_user():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'user: "10001:10001"' in compose
    assert "127.0.0.1:7331:7331" in compose
    assert "healthcheck:" in compose
    assert "http://127.0.0.1:7331/health" in compose


def test_dockerignore_excludes_local_runtime_artifacts():
    root = Path(__file__).resolve().parents[1]
    dockerignore = (root / ".dockerignore").read_text(encoding="utf-8")

    for pattern in [".venv/", ".pytest_cache/", ".tmp/", ".ctx-engine-data/", ".ctx-engine/", "HOME_CONTINUE/", "output/", "__pycache__/", "*.pyc"]:
        assert pattern in dockerignore


def test_windows_docker_smoke_script_checks_runtime_contract():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "docker_smoke.ps1").read_text(encoding="utf-8")

    assert "param(" in script
    assert "docker compose" in script
    assert "http://127.0.0.1:7331/health" in script
    assert "http://127.0.0.1:7331/dashboard/status" in script
    assert "mcp-check --endpoint" in script
    assert "10001:10001" in script
    assert "/workspace read-only" in script
    assert "/data" in script


def test_client_and_external_runtime_smoke_scripts_exist():
    root = Path(__file__).resolve().parents[1]
    client = (root / "scripts" / "client_smoke.ps1").read_text(encoding="utf-8")
    external = (root / "scripts" / "external_runtime_smoke.ps1").read_text(encoding="utf-8")
    quality = (root / "scripts" / "quality_gate.ps1").read_text(encoding="utf-8")

    assert "client-check" in client
    assert "claude mcp get ctx-engine" in client
    assert "gemini mcp list" in client
    assert "Kuzu real-runtime smoke" in external
    assert "CTX_ENGINE_HINDSIGHT_ENDPOINT" in external
    assert "CTX_ENGINE_LSP_" in external
    assert "CTX_ENGINE_SCIP_" in external
    assert "mcp-lint --strict" in quality
    assert "ci status" in quality
    assert "structural-search" in quality
    assert "docker_smoke.ps1" in quality
