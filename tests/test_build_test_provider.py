from __future__ import annotations

from ctx_engine.providers.build_test import BuildTestProvider


def test_build_test_provider_suggests_docker_smoke_for_compose_repo():
    result = BuildTestProvider().detect(".")

    commands = {item["name"]: item for item in result["commands"]}
    assert "docker-smoke" in commands
    assert commands["docker-smoke"]["command"] == ".\\scripts\\docker_smoke.ps1"
    assert "docker-compose" in result["evidence"]
    assert "GitHub Actions" in result["evidence"]


def test_build_test_provider_links_python_source_to_importing_test(fixture_root):
    result = BuildTestProvider().detect(fixture_root / "python_app", ["app/middleware.py"])

    assert "tests/test_auth.py" in result["suggested_tests"]
    assert result["test_plan"][0]["command"] == "pytest tests/test_auth.py"
    assert result["test_plan"][0]["source_files"] == ["app/middleware.py"]


def test_build_test_provider_links_ts_source_to_importing_test(fixture_root):
    result = BuildTestProvider().detect(fixture_root / "ts_app", ["src/auth.ts"])

    assert "tests/auth.test.ts" in result["suggested_tests"]
    assert result["test_plan"][0]["command"] == "npm run test -- tests/auth.test.ts"
    assert result["test_plan"][0]["source"] == "package.json"
