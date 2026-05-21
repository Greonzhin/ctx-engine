from __future__ import annotations

from ctx_engine.retrieval_benchmark import run_retrieval_benchmark


def test_retrieval_benchmark_from_cases_file(tmp_path, fixture_root):
    cases = tmp_path / "cases.json"
    cases.write_text(
        '[{"query":"authenticate_request","expected":"authenticate_request"},{"query":"AuthMiddleware","expected":"AuthMiddleware"}]',
        encoding="utf-8",
    )
    result = run_retrieval_benchmark(
        path=fixture_root / "python_app",
        cases_file=cases,
        top_k=3,
    )
    assert result["status"] == "ok"
    assert result["cases_total"] == 2
    assert result["metrics"]["top1_ratio"] >= 0.5
    assert result["metrics"]["top3_ratio"] >= result["metrics"]["top1_ratio"]


def test_retrieval_benchmark_default_cases(fixture_root):
    indexed = run_retrieval_benchmark(path=fixture_root / "python_app", top_k=3)
    assert indexed["status"] == "ok"
    assert indexed["cases_total"] >= 1


def test_retrieval_benchmark_semantic_quality_gate_python(tmp_path, fixture_root):
    cases = tmp_path / "py_cases.json"
    cases.write_text(
        '[{"query":"authenticate_request","expected":"authenticate_request"},'
        '{"query":"auth request","expected":"authenticate_request"},'
        '{"query":"test auth","expected":"test_authenticate_request_accepts_valid_token"}]',
        encoding="utf-8",
    )
    result = run_retrieval_benchmark(path=fixture_root / "python_app", cases_file=cases, top_k=3)
    assert result["status"] == "ok"
    assert result["cases_total"] == 3
    assert result["metrics"]["top1_ratio"] >= 0.66
    assert result["metrics"]["top3_ratio"] >= 1.0


def test_retrieval_benchmark_semantic_quality_gate_typescript(tmp_path, fixture_root):
    cases = tmp_path / "ts_cases.json"
    cases.write_text(
        '[{"query":"authenticateToken","expected":"authenticateToken"},'
        '{"query":"impact auth","expected":"authenticateToken"},'
        '{"query":"test auth","expected":"authenticateToken accepts valid token"}]',
        encoding="utf-8",
    )
    result = run_retrieval_benchmark(path=fixture_root / "ts_app", cases_file=cases, top_k=3)
    assert result["status"] == "ok"
    assert result["cases_total"] == 3
    assert result["metrics"]["top1_ratio"] >= 0.66
    assert result["metrics"]["top3_ratio"] >= 1.0
