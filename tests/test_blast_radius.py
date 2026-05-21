from __future__ import annotations

from ctx_engine.providers.code_graph import CodeGraphProvider


def test_blast_radius_returns_related_files_and_confidence(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    payload = CodeGraphProvider().blast_radius("authenticate_request", workspace_id=result["workspace_id"], depth=1, limit=20)

    assert payload["status"] == "ok"
    assert payload["seeds"]
    assert payload["related_files"]
    assert any(item["path"].endswith("app/middleware.py") for item in payload["related_files"])
    assert all(item.get("confidence_label") in {"extracted", "inferred", "ambiguous"} for item in payload["related_files"])
    assert all(item.get("semantic_confidence") in {"extracted", "inferred", "ambiguous"} for item in payload["related_files"])
    assert all(isinstance(item.get("edge_evidence"), list) for item in payload["related_files"])
