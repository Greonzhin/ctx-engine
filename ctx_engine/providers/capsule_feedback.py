from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from typing import Any

from ..db import connect, init_db, now_iso, stable_json
from .action_ledger import ActionLedger


VALID_FEEDBACK_RATINGS = ("useful", "partial", "miss")


def feedback_id(capsule_id: str, timestamp: str, client_id: str) -> str:
    raw = f"{capsule_id}:{timestamp}:{client_id}:{time.time_ns()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


class CapsuleFeedbackProvider:
    def __init__(self) -> None:
        self.ledger = ActionLedger()

    def record(
        self,
        capsule_id: str,
        rating: str,
        workspace_id: str | None = None,
        client_id: str = "cli",
        useful_files: list[str] | None = None,
        missing_files: list[str] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        capsule_id = capsule_id.strip()
        rating = rating.strip().lower()
        if not capsule_id:
            raise ValueError("capsule_id is required")
        if rating not in VALID_FEEDBACK_RATINGS:
            raise ValueError(f"rating must be one of: {', '.join(VALID_FEEDBACK_RATINGS)}")

        useful = sorted({item for item in (useful_files or []) if item})
        missing = sorted({item for item in (missing_files or []) if item})
        timestamp = now_iso()
        fid = feedback_id(capsule_id, timestamp, client_id)
        ledger_id = self.ledger.record(
            "capsule_feedback",
            f"feedback {rating} for capsule {capsule_id}",
            {
                "capsule_id": capsule_id,
                "rating": rating,
                "useful_files": useful,
                "missing_files": missing,
            },
            client_id=client_id,
            workspace_id=workspace_id,
        )

        conn = init_db(connect())
        try:
            conn.execute(
                """
                INSERT INTO capsule_feedback(
                  id, timestamp, capsule_id, workspace_id, client_id, rating,
                  useful_files_json, missing_files_json, notes, ledger_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    timestamp,
                    capsule_id,
                    workspace_id,
                    client_id,
                    rating,
                    stable_json(useful),
                    stable_json(missing),
                    notes.strip(),
                    ledger_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "status": "ok",
            "id": fid,
            "timestamp": timestamp,
            "capsule_id": capsule_id,
            "workspace_id": workspace_id,
            "client_id": client_id,
            "rating": rating,
            "useful_files": useful,
            "missing_files": missing,
            "notes": notes.strip(),
            "ledger_id": ledger_id,
        }

    def report(
        self,
        capsule_id: str | None = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        rows = self._query(capsule_id=capsule_id, workspace_id=workspace_id, limit=limit)
        rating_counts = Counter(str(row["rating"]) for row in rows)
        useful_counts = Counter(file for row in rows for file in row["useful_files"])
        missing_counts = Counter(file for row in rows for file in row["missing_files"])
        return {
            "status": "ok",
            "filters": {"capsule_id": capsule_id, "workspace_id": workspace_id, "limit": limit},
            "summary": {
                "feedback_count": len(rows),
                "rating_counts": {rating: rating_counts.get(rating, 0) for rating in VALID_FEEDBACK_RATINGS},
                "top_useful_files": self._top_files(useful_counts),
                "top_missing_files": self._top_files(missing_counts),
            },
            "feedback": rows,
        }

    def summary(self, capsule_id: str, workspace_id: str | None = None) -> dict[str, Any]:
        rows = self._query(capsule_id=capsule_id, workspace_id=workspace_id, limit=100)
        rating_counts = Counter(str(row["rating"]) for row in rows)
        latest = rows[0] if rows else None
        return {
            "status": "ok",
            "capsule_id": capsule_id,
            "feedback_count": len(rows),
            "rating_counts": {rating: rating_counts.get(rating, 0) for rating in VALID_FEEDBACK_RATINGS},
            "latest_rating": latest["rating"] if latest else None,
            "latest_at": latest["timestamp"] if latest else None,
        }

    def _query(
        self,
        capsule_id: str | None = None,
        workspace_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[object] = []
        if capsule_id:
            clauses.append("capsule_id = ?")
            values.append(capsule_id)
        if workspace_id:
            clauses.append("workspace_id = ?")
            values.append(workspace_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, int(limit)))
        conn = init_db(connect())
        try:
            rows = conn.execute(
                f"SELECT * FROM capsule_feedback {where} ORDER BY timestamp DESC LIMIT ?",
                values,
            ).fetchall()
            return [self._row(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        data = dict(row)
        data["useful_files"] = json.loads(data.pop("useful_files_json") or "[]")
        data["missing_files"] = json.loads(data.pop("missing_files_json") or "[]")
        return data

    @staticmethod
    def _top_files(counts: Counter[str]) -> list[dict[str, object]]:
        return [{"path": path, "count": count} for path, count in counts.most_common(10)]
