from __future__ import annotations

from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.memory import BuiltInMemoryProvider


def test_memory_lifecycle_policy_and_namespace(fixture_root):
    result = CodeGraphProvider().index_repository(fixture_root / "python_app")
    provider = BuiltInMemoryProvider()

    hot = provider.retain(
        "critical auth note",
        workspace_id=result["workspace_id"],
        lifecycle_tier="hot",
        agent_namespace="agent-a",
    )
    cold = provider.retain(
        "old auth note",
        workspace_id=result["workspace_id"],
        lifecycle_tier="cold",
        agent_namespace="agent-a",
    )
    other = provider.retain(
        "other namespace note",
        workspace_id=result["workspace_id"],
        lifecycle_tier="warm",
        agent_namespace="agent-b",
    )
    assert hot["lifecycle_tier"] == "hot"
    assert cold["lifecycle_tier"] == "cold"
    assert other["agent_namespace"] == "agent-b"

    only_agent_a = provider.recall("auth", workspace_id=result["workspace_id"], agent_namespace="agent-a")
    assert only_agent_a
    assert all(item["agent_namespace"] == "agent-a" for item in only_agent_a)

    policy = provider.apply_lifecycle_policy(
        workspace_id=result["workspace_id"],
        agent_namespace="agent-a",
        hot_days=0,
        warm_days=0,
    )
    assert policy["status"] == "ok"
    assert policy["updated"] >= 2
    assert set(policy["counts"]).issuperset({"hot", "warm", "cold"})

