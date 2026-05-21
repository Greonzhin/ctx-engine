from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

from ..db import connect, init_db, now_iso
from ..workspace import get_workspace


def _event_id(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def query_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return int(values[0])
    ordered = sorted(values)
    pos = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return int(ordered[lower])
    weight = pos - lower
    return int(round(ordered[lower] * (1 - weight) + ordered[upper] * weight))


class EgressProvider:
    def record(
        self,
        provider: str,
        query: str,
        endpoint: str,
        status: str,
        latency_ms: int,
        response_bytes: int,
        cache_hit: bool = False,
        workspace_id: str | None = None,
        library_id: str | None = None,
    ) -> dict[str, object]:
        workspace = get_workspace(workspace_id)
        wid = str(workspace["id"]) if workspace else None
        endpoint_host = urlparse(endpoint).hostname
        hashed = query_hash(query)
        timestamp = now_iso()
        identity = _event_id(
            f"{provider}:{wid}:{library_id}:{hashed}:{status}:{latency_ms}:{response_bytes}:{cache_hit}:{timestamp}"
        )
        conn = init_db(connect())
        try:
            conn.execute(
                """
                INSERT INTO egress_events(
                  id, provider, workspace_id, library_id, query_hash, endpoint_host, status, latency_ms,
                  response_bytes, cache_hit, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity,
                    provider,
                    wid,
                    library_id,
                    hashed,
                    endpoint_host,
                    status,
                    int(latency_ms),
                    int(response_bytes),
                    1 if cache_hit else 0,
                    timestamp,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {"id": identity, "provider": provider, "status": status}

    def report(
        self,
        since: str | None = None,
        limit: int = 100,
        provider: str | None = None,
    ) -> dict[str, object]:
        conn = init_db(connect())
        params: list[object] = []
        where: list[str] = []
        if since:
            where.append("timestamp >= ?")
            params.append(since)
        if provider:
            where.append("provider = ?")
            params.append(provider)
        sql = """
            SELECT id, provider, workspace_id, library_id, query_hash, endpoint_host, status, latency_ms,
                   response_bytes, cache_hit, timestamp
            FROM egress_events
        """
        if where:
            sql += f" WHERE {' AND '.join(where)}"
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        try:
            rows = [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
        finally:
            conn.close()
        success = sum(1 for row in rows if str(row.get("status", "")).startswith("ok"))
        failed = len(rows) - success
        by_status: dict[str, int] = {}
        latencies: list[int] = []
        cache_hits = 0
        for row in rows:
            status_key = str(row.get("status") or "unknown")
            by_status[status_key] = int(by_status.get(status_key, 0)) + 1
            latencies.append(int(row.get("latency_ms") or 0))
            if int(row.get("cache_hit") or 0) == 1:
                cache_hits += 1
        cache_hit_rate = round(cache_hits / len(rows), 4) if rows else 0.0
        return {
            "status": "ok",
            "filters": {"since": since, "limit": limit, "provider": provider},
            "summary": {
                "events": len(rows),
                "success": success,
                "failed": failed,
                "by_status": by_status,
                "p50_latency_ms": _percentile(latencies, 0.50),
                "p95_latency_ms": _percentile(latencies, 0.95),
                "cache_hit_rate": cache_hit_rate,
            },
            "events": rows,
        }

    def summary_last_24h(self, provider: str | None = None) -> dict[str, object]:
        conn = init_db(connect())
        params: list[object] = []
        where = "timestamp >= datetime('now', '-1 day')"
        if provider:
            where += " AND provider = ?"
            params.append(provider)
        try:
            rows = conn.execute(
                f"""
                SELECT status, COUNT(*) AS count
                FROM egress_events
                WHERE {where}
                GROUP BY status
                """,
                tuple(params),
            ).fetchall()
            last_row = conn.execute(
                f"""
                SELECT timestamp
                FROM egress_events
                WHERE {where}
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        finally:
            conn.close()
        total = 0
        success = 0
        failed = 0
        for row in rows:
            count = int(row["count"])
            total += count
            if str(row["status"]).startswith("ok"):
                success += count
            else:
                failed += count
        error_ratio = round((failed / total), 4) if total else 0.0
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "last_context7_event_at": (str(last_row["timestamp"]) if last_row else None),
            "context7_error_ratio_24h": error_ratio,
        }
