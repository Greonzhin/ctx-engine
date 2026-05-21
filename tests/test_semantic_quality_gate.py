from __future__ import annotations

from collections import Counter

from ctx_engine.providers.code_graph import CodeGraphProvider


def _top_hits(items: list[str], expected: str, top_k: int = 3) -> tuple[bool, bool]:
    top1 = bool(items and items[0] == expected)
    topk = expected in items[:top_k]
    return top1, topk


def test_semantic_refs_quality_gate_fixture_matrix(fixture_root):
    provider = CodeGraphProvider()
    py = provider.index_repository(fixture_root / "python_app")
    ts = provider.index_repository(fixture_root / "ts_app")
    cases = [
        (str(py["workspace_id"]), "authenticate_request", "authenticate_request"),
        (str(py["workspace_id"]), "test auth", "test_authenticate_request_accepts_valid_token"),
        (str(ts["workspace_id"]), "authenticateToken", "authenticateToken"),
        (str(ts["workspace_id"]), "test auth", "authenticateToken accepts valid token"),
    ]
    top1_hits = 0
    top3_hits = 0
    confidence = Counter()

    for wid, query, expected in cases:
        payload = provider.get_symbol_references(query, workspace_id=wid, depth=1, limit=20)
        refs = payload.get("references", [])
        names = [str(item.get("symbol") or "") for item in refs]
        top1, top3 = _top_hits(names, expected, top_k=3)
        if top1:
            top1_hits += 1
        if top3:
            top3_hits += 1
        assert refs, f"no refs for query={query}"
        assert any(list(item.get("edge_evidence") or []) for item in refs[:3]), f"missing edge evidence for query={query}"
        for item in refs[:3]:
            confidence[str(item.get("semantic_confidence") or "ambiguous")] += 1

    total = len(cases)
    assert top1_hits / total >= 0.75
    assert top3_hits / total >= 1.0
    strong = confidence["extracted"] + confidence["inferred"]
    all_top = sum(confidence.values()) or 1
    assert strong / all_top >= 0.8


def test_semantic_impact_quality_gate_fixture_matrix(fixture_root):
    provider = CodeGraphProvider()
    py = provider.index_repository(fixture_root / "python_app")
    ts = provider.index_repository(fixture_root / "ts_app")
    cases = [
        (str(py["workspace_id"]), "authenticate_request", "tests/test_auth.py"),
        (str(ts["workspace_id"]), "authenticateToken", "tests/auth.test.ts"),
        (str(ts["workspace_id"]), "impact auth", "tests/auth.test.ts"),
    ]
    top1_hits = 0
    top3_hits = 0

    for wid, query, expected_path in cases:
        payload = provider.get_change_impact(query, workspace_id=wid, depth=1, limit=20, include_tests=True)
        impacted = payload.get("impacted_files", [])
        paths = [str(item.get("path") or "") for item in impacted]
        top1, top3 = _top_hits(paths, expected_path, top_k=3)
        if top1:
            top1_hits += 1
        if top3:
            top3_hits += 1
        assert impacted, f"no impacted files for query={query}"
        assert any(list(item.get("edge_evidence") or []) for item in impacted[:3]), f"missing impact evidence for query={query}"

    total = len(cases)
    assert top1_hits / total >= 0.66
    assert top3_hits / total >= 1.0

