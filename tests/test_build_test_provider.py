from __future__ import annotations

from ctx_engine.providers.build_test import BuildTestProvider


def test_build_test_provider_suggests_docker_smoke_for_compose_repo():
    result = BuildTestProvider().detect(".")

    commands = {item["name"]: item for item in result["commands"]}
    assert "docker-smoke" in commands
    assert commands["docker-smoke"]["command"] == ".\\scripts\\docker_smoke.ps1"
    assert "docker-compose" in result["evidence"]
    assert "GitHub Actions" in result["evidence"]
