from __future__ import annotations

from ctx_engine.benchmark import benchmark_capsule


def test_benchmark_reports_local_token_counts(fixture_root):
    result = benchmark_capsule(
        "authenticate request",
        path=fixture_root / "python_app",
        token_budget=1200,
    )

    assert result["status"] == "ok"
    assert result["baseline"]["files"] >= 2
    assert result["baseline"]["total_tokens"] > 0
    assert result["capsule"]["selected_file_count"] >= 1
    assert result["capsule"]["context_total_tokens"] > 0
    assert result["capsule"]["transport_total_tokens"] >= result["capsule"]["context_total_tokens"]
    assert result["reduction"]["ratio"] is not None
    assert result["index_fingerprint"]["combined_index_hash"]
