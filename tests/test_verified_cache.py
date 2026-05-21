from __future__ import annotations

import json

from ctx_engine.capsule.builder import CapsuleBuilder
from ctx_engine.cli import main
from ctx_engine.providers.cache import CacheProvider, capsule_namespace
from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.local_docs import LocalDocsProvider
from ctx_engine.verified_cache import verify_capsule_cache


def _indexed_workspace(root):
    result = CodeGraphProvider().index_repository(root)
    LocalDocsProvider().index(root, result["workspace_id"])
    return result["workspace_id"]


def test_verified_cache_reports_valid_capsule_cache(fixture_root):
    workspace_id = _indexed_workspace(fixture_root / "python_app")
    CapsuleBuilder().build("authenticate request", workspace_id=workspace_id)

    result = verify_capsule_cache(workspace_id)

    assert result["status"] == "ok"
    assert result["summary"]["entry_count"] == 1
    assert result["summary"]["valid"] == 1
    assert result["entries"][0]["status"] == "valid"
    assert result["entries"][0]["evidence"]


def test_verified_cache_reports_stale_entry(fixture_root):
    workspace_id = _indexed_workspace(fixture_root / "python_app")
    CacheProvider().set(
        capsule_namespace(workspace_id),
        {"test": "stale"},
        {
            "task_brief": "old cache",
            "workspace_id": workspace_id,
            "index_fingerprint": {"combined_index_hash": "old"},
            "provenance": {"capsule_id": "stale-capsule"},
        },
    )

    result = verify_capsule_cache(workspace_id)

    assert result["status"] == "stale"
    assert result["summary"]["stale"] == 1
    assert result["entries"][0]["capsule_id"] == "stale-capsule"


def test_verified_cache_cli_strict_fails_on_stale(fixture_root, capsys):
    workspace_id = _indexed_workspace(fixture_root / "python_app")
    CacheProvider().set(
        capsule_namespace(workspace_id),
        {"test": "stale-cli"},
        {
            "workspace_id": workspace_id,
            "index_fingerprint": {"combined_index_hash": "old"},
            "provenance": {"capsule_id": "stale-cli"},
        },
    )

    assert main(["cache", "verify", workspace_id]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "stale"

    assert main(["cache", "verify", workspace_id, "--strict"]) == 1
    strict_payload = json.loads(capsys.readouterr().out)
    assert strict_payload["summary"]["stale"] == 1
