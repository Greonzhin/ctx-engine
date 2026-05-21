from __future__ import annotations

from ctx_engine.doctor import doctor_status
from ctx_engine.providers.egress import EgressProvider


def test_egress_report_shape_for_zero_events():
    report = EgressProvider().report(provider="context7", limit=5)
    assert report["status"] == "ok"
    assert report["summary"]["events"] == 0
    assert report["summary"]["by_status"] == {}
    assert report["summary"]["p50_latency_ms"] == 0
    assert report["summary"]["p95_latency_ms"] == 0
    assert report["summary"]["cache_hit_rate"] == 0.0


def test_egress_report_and_doctor_summary(tmp_path):
    provider = EgressProvider()
    provider.record(
        provider="context7",
        query="fastapi auth",
        endpoint="https://mcp.context7.com/mcp",
        status="ok_live",
        latency_ms=42,
        response_bytes=1024,
        cache_hit=False,
    )
    provider.record(
        provider="context7",
        query="fastapi auth",
        endpoint="https://mcp.context7.com/mcp",
        status="ok_cache_hit",
        latency_ms=1,
        response_bytes=512,
        cache_hit=True,
    )
    report = provider.report(provider="context7", limit=5)
    assert report["status"] == "ok"
    assert report["summary"]["events"] >= 1
    assert "by_status" in report["summary"]
    assert report["summary"]["p50_latency_ms"] >= 0
    assert report["summary"]["p95_latency_ms"] >= report["summary"]["p50_latency_ms"]
    assert report["summary"]["cache_hit_rate"] > 0
    event = report["events"][0]
    assert event["provider"] == "context7"
    assert event["query_hash"] != "fastapi auth"
    assert len(event["query_hash"]) == 64

    health = doctor_status(tmp_path)
    assert "egress_last_24h" in health["checks"]
    assert int(health["checks"]["egress_last_24h"]["total"]) >= 1
    assert "last_context7_event_at" in health["checks"]["egress_last_24h"]
    assert "context7_error_ratio_24h" in health["checks"]["egress_last_24h"]
