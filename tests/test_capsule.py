from __future__ import annotations

import shutil

from ctx_engine.capsule.builder import CapsuleBuilder
from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.local_docs import LocalDocsProvider


def test_capsule_returns_required_fields_under_budget(fixture_root):
    root = fixture_root / "python_app"
    result = CodeGraphProvider().index_repository(root)
    LocalDocsProvider().index(root, result["workspace_id"])
    capsule = CapsuleBuilder().build("where is auth handled?", token_budget=1200, workspace_id=result["workspace_id"])
    assert capsule["workspace_id"] == result["workspace_id"]
    assert capsule["selected_files"]
    assert capsule["ledger_id"]
    assert "build_test_context" in capsule
    assert "test_plan" in capsule["build_test_context"]
    assert "app/middleware.py" in {item["path"] for item in capsule["selected_files"]}
    assert any(item["command"] == "pytest tests/test_auth.py" for item in capsule["build_test_context"]["test_plan"])
    assert all(item.get("confidence_label") in {"extracted", "inferred", "ambiguous"} for item in capsule["selected_files"])
    assert all(item.get("confidence_label") in {"extracted", "inferred", "ambiguous"} for item in capsule["selected_symbols"])
    assert all(item.get("semantic_confidence") in {"extracted", "inferred", "ambiguous"} for item in capsule["selected_files"])
    assert all(item.get("semantic_confidence") in {"extracted", "inferred", "ambiguous"} for item in capsule["selected_symbols"])
    assert all(isinstance(item.get("edge_evidence"), list) for item in capsule["selected_symbols"])


def test_capsule_cache_is_invalidated_by_index_hash(tmp_path, fixture_root):
    root = tmp_path / "python_app"
    shutil.copytree(fixture_root / "python_app", root)

    result = CodeGraphProvider().index_repository(root)
    LocalDocsProvider().index(root, result["workspace_id"])
    first = CapsuleBuilder().build("authenticate request", token_budget=1200, workspace_id=result["workspace_id"])
    second = CapsuleBuilder().build("authenticate request", token_budget=1200, workspace_id=result["workspace_id"])
    assert first["cache"] == "miss"
    assert second["cache"] == "hit"
    first_hash = first["index_fingerprint"]["combined_index_hash"]

    middleware = root / "app" / "middleware.py"
    middleware.write_text(
        middleware.read_text(encoding="utf-8") + "\n\ndef authenticate_extra():\n    return True\n",
        encoding="utf-8",
    )
    result = CodeGraphProvider().index_repository(root)
    LocalDocsProvider().index(root, result["workspace_id"])
    third = CapsuleBuilder().build("authenticate request", token_budget=1200, workspace_id=result["workspace_id"])

    assert third["cache"] == "miss"
    assert third["index_fingerprint"]["combined_index_hash"] != first_hash


def test_capsule_cache_invalidation_is_workspace_scoped(tmp_path, fixture_root):
    root_a = tmp_path / "python_app_a"
    root_b = tmp_path / "python_app_b"
    shutil.copytree(fixture_root / "python_app", root_a)
    shutil.copytree(fixture_root / "python_app", root_b)

    result_a = CodeGraphProvider().index_repository(root_a)
    LocalDocsProvider().index(root_a, result_a["workspace_id"])
    result_b = CodeGraphProvider().index_repository(root_b)
    LocalDocsProvider().index(root_b, result_b["workspace_id"])

    query = "authenticate request"
    CapsuleBuilder().build(query, token_budget=1200, workspace_id=result_a["workspace_id"])
    CapsuleBuilder().build(query, token_budget=1200, workspace_id=result_b["workspace_id"])
    second_a = CapsuleBuilder().build(query, token_budget=1200, workspace_id=result_a["workspace_id"])
    second_b = CapsuleBuilder().build(query, token_budget=1200, workspace_id=result_b["workspace_id"])
    assert second_a["cache"] == "hit"
    assert second_b["cache"] == "hit"

    middleware = root_a / "app" / "middleware.py"
    middleware.write_text(
        middleware.read_text(encoding="utf-8") + "\n\ndef authenticate_workspace_a_only():\n    return True\n",
        encoding="utf-8",
    )
    result_a = CodeGraphProvider().index_repository(root_a)
    LocalDocsProvider().index(root_a, result_a["workspace_id"])

    third_a = CapsuleBuilder().build(query, token_budget=1200, workspace_id=result_a["workspace_id"])
    third_b = CapsuleBuilder().build(query, token_budget=1200, workspace_id=result_b["workspace_id"])
    assert third_a["cache"] == "miss"
    assert third_b["cache"] == "hit"
