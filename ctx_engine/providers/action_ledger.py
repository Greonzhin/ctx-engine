from __future__ import annotations

import hashlib
import json
import time

from ..db import connect, init_db, now_iso, stable_json


def ledger_id(event_type: str, timestamp: str, summary: str, nonce: int | None = None) -> str:
    raw = f"{timestamp}:{event_type}:{summary}:{nonce if nonce is not None else ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


class ActionLedger:
    def record(
        self,
        event_type: str,
        summary: str,
        data: dict[str, object] | None = None,
        client_id: str = "generic",
        workspace_id: str | None = None,
    ) -> str:
        timestamp = now_iso()
        lid = ledger_id(event_type, timestamp, summary, time.time_ns())
        conn = init_db(connect())
        try:
            conn.execute(
                """
                INSERT INTO action_ledger(id, timestamp, client_id, workspace_id, event_type, summary, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (lid, timestamp, client_id, workspace_id, event_type, summary, stable_json(data or {})),
            )
            conn.commit()
            return lid
        finally:
            conn.close()

    def tail(self, limit: int = 20, query: str = "") -> list[dict[str, object]]:
        conn = init_db(connect())
        try:
            if query:
                rows = conn.execute(
                    """
                    SELECT * FROM action_ledger
                    WHERE summary LIKE ? OR event_type LIKE ? OR data_json LIKE ?
                    ORDER BY timestamp DESC LIMIT ?
                    """,
                    (f"%{query}%", f"%{query}%", f"%{query}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM action_ledger ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
            return [self._row(row) for row in rows]
        finally:
            conn.close()

    def show(self, ledger_id_value: str) -> dict[str, object] | None:
        conn = init_db(connect())
        try:
            row = conn.execute(
                "SELECT * FROM action_ledger WHERE id = ?", (ledger_id_value,)
            ).fetchone()
            return self._row(row) if row else None
        finally:
            conn.close()

    def export(self) -> list[dict[str, object]]:
        conn = init_db(connect())
        try:
            rows = conn.execute("SELECT * FROM action_ledger ORDER BY timestamp").fetchall()
            return [self._row(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _row(row) -> dict[str, object]:
        data = dict(row)
        data["data"] = json.loads(data.pop("data_json") or "{}")
        return data
