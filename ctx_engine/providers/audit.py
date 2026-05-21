from __future__ import annotations

from .action_ledger import ActionLedger


class AuditProvider:
    def __init__(self) -> None:
        self.ledger = ActionLedger()

    def note(self, summary: str, data: dict[str, object] | None = None, client_id: str = "generic", workspace_id: str | None = None) -> str:
        return self.ledger.record("audit", summary, data or {}, client_id=client_id, workspace_id=workspace_id)
