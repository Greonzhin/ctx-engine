from __future__ import annotations

from ctx_engine.providers.action_ledger import ActionLedger


def test_action_ledger_allows_repeated_event_summaries():
    ledger = ActionLedger()
    first = ledger.record("capsule", "same summary", {"same": True})
    second = ledger.record("capsule", "same summary", {"same": True})

    assert first != second
    assert ledger.show(first)
    assert ledger.show(second)
