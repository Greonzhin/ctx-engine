from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from ..db import connect, init_db, now_iso, stable_json
from ..integrations.hindsight import ExternalHindsightUnavailable, HindsightAdapter
from ..workspace import get_workspace


def memory_id(workspace_id: str, claim: str, source: str) -> str:
    return hashlib.sha256(f"{workspace_id}:{claim}:{source}".encode("utf-8")).hexdigest()[:24]


class BuiltInMemoryProvider:
    def __init__(self) -> None:
        self._hindsight = HindsightAdapter()

    @staticmethod
    def _normalize_tier(value: str | None) -> str:
        tier = (value or "").strip().lower()
        if tier in {"hot", "warm", "cold"}:
            return tier
        default_tier = (os.environ.get("CTX_ENGINE_MEMORY_DEFAULT_TIER", "warm") or "warm").strip().lower()
        return default_tier if default_tier in {"hot", "warm", "cold"} else "warm"

    @staticmethod
    def _provider_name() -> str:
        return (os.environ.get("CTX_ENGINE_MEMORY_PROVIDER", "sqlite") or "sqlite").strip().lower()

    @staticmethod
    def _fallback_warning(reason: str | None) -> str:
        return f"{reason or 'External Hindsight runtime is unavailable.'} Using sqlite fallback."

    def _selected_hindsight(self) -> bool:
        return self._provider_name() == "hindsight"

    def retain(
        self,
        claim: str,
        workspace_id: str | None = None,
        scope: str = "project",
        source: str = "user",
        files: list[str] | None = None,
        symbols: list[str] | None = None,
        docs: list[str] | None = None,
        confidence: float = 0.6,
        lifecycle_tier: str | None = None,
        agent_namespace: str = "default",
    ) -> dict[str, object]:
        if self._selected_hindsight():
            available, reason = self._hindsight.status()
            if available:
                try:
                    return self._hindsight.retain(
                        claim,
                        workspace_id=workspace_id,
                        scope=scope,
                        source=source,
                        files=files,
                        symbols=symbols,
                        docs=docs,
                        confidence=confidence,
                        lifecycle_tier=lifecycle_tier,
                        agent_namespace=agent_namespace,
                    )
                except ExternalHindsightUnavailable as exc:
                    reason = str(exc)
            data = self._retain_sqlite(
                claim,
                workspace_id=workspace_id,
                scope=scope,
                source=source,
                files=files,
                symbols=symbols,
                docs=docs,
                confidence=confidence,
                lifecycle_tier=lifecycle_tier,
                agent_namespace=agent_namespace,
            )
            data["provider_warning"] = self._fallback_warning(reason)
            data["provider_used"] = "sqlite_fallback"
            return data
        data = self._retain_sqlite(
            claim,
            workspace_id=workspace_id,
            scope=scope,
            source=source,
            files=files,
            symbols=symbols,
            docs=docs,
            confidence=confidence,
            lifecycle_tier=lifecycle_tier,
            agent_namespace=agent_namespace,
        )
        data["provider_used"] = "sqlite"
        return data

    def recall(
        self,
        query: str = "",
        workspace_id: str | None = None,
        scope: str = "project",
        limit: int = 10,
        agent_namespace: str = "default",
    ) -> list[dict[str, object]]:
        warning: str | None = None
        if self._selected_hindsight():
            available, reason = self._hindsight.status()
            if available:
                try:
                    rows = self._hindsight.recall(
                        query=query,
                        workspace_id=workspace_id,
                        scope=scope,
                        limit=limit,
                        agent_namespace=agent_namespace,
                    )
                    for row in rows:
                        row["provider_used"] = "hindsight"
                    return rows
                except ExternalHindsightUnavailable as exc:
                    reason = str(exc)
            warning = self._fallback_warning(reason)
        rows = self._recall_sqlite(query, workspace_id, scope, limit, agent_namespace)
        provider = "sqlite_fallback" if warning else "sqlite"
        for row in rows:
            row["provider_used"] = provider
            if warning:
                row["provider_warning"] = warning
        return rows

    def reflect(self, workspace_id: str | None = None) -> dict[str, object]:
        memories = self.recall("", workspace_id, limit=50)
        return {"count": len(memories), "summary": f"{len(memories)} active project memories"}

    def report(
        self,
        workspace_id: str | None = None,
        agent_namespace: str | None = None,
        limit: int = 10,
    ) -> dict[str, object]:
        workspace = get_workspace(workspace_id)
        wid = str(workspace["id"]) if workspace else "global"
        namespace = (agent_namespace or "").strip() or None
        conn = init_db(connect())
        try:
            params: list[object] = [wid]
            namespace_clause = ""
            if namespace:
                namespace_clause = " AND agent_namespace = ?"
                params.append(namespace)
            rows = conn.execute(
                f"""
                SELECT *
                FROM memories
                WHERE workspace_id = ?{namespace_clause}
                ORDER BY created_at DESC
                """,
                tuple(params),
            ).fetchall()
        finally:
            conn.close()

        items = [self._row(row) for row in rows]
        active = [item for item in items if not item.get("superseded_by")]
        lifecycle_counts = Counter(str(item.get("lifecycle_tier") or "unknown") for item in active)
        trust_counts = Counter(str(item.get("trust_tier") or "unknown") for item in active)
        source_counts = Counter(str(item.get("source") or "unknown") for item in active)
        namespace_counts = Counter(str(item.get("agent_namespace") or "default") for item in active)

        claim_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
        for item in active:
            claim_groups[self._claim_key(str(item.get("claim") or ""))].append(item)
        conflict_candidates = [
            {
                "claim_key": key,
                "count": len(group),
                "memory_ids": [str(item.get("id")) for item in group[:limit]],
                "claims": [str(item.get("claim")) for item in group[:limit]],
            }
            for key, group in sorted(claim_groups.items())
            if key and len(group) > 1
        ]

        unverified = [item for item in active if str(item.get("trust_tier")) != "verified"]
        recent = [
            {
                "id": item.get("id"),
                "claim": item.get("claim"),
                "trust_tier": item.get("trust_tier"),
                "lifecycle_tier": item.get("lifecycle_tier"),
                "agent_namespace": item.get("agent_namespace"),
                "created_at": item.get("created_at"),
                "last_verified_at": item.get("last_verified_at"),
                "superseded_by": item.get("superseded_by"),
            }
            for item in items[:limit]
        ]
        return {
            "status": "ok",
            "provider_used": "sqlite",
            "workspace_id": wid,
            "agent_namespace": namespace,
            "summary": {
                "total": len(items),
                "active": len(active),
                "superseded": len(items) - len(active),
                "unverified": len(unverified),
                "verified": trust_counts.get("verified", 0),
                "conflict_candidates": len(conflict_candidates),
                "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
                "trust_counts": dict(sorted(trust_counts.items())),
                "source_counts": dict(sorted(source_counts.items())),
                "namespace_counts": dict(sorted(namespace_counts.items())),
            },
            "unverified_samples": [
                {"id": item.get("id"), "claim": item.get("claim"), "trust_tier": item.get("trust_tier")}
                for item in unverified[:limit]
            ],
            "conflict_candidates": conflict_candidates[:limit],
            "recent": recent,
        }

    def verify(self, memory_id_value: str, evidence: str) -> dict[str, object] | None:
        evidence_hash = hashlib.sha256(evidence.encode("utf-8")).hexdigest()
        conn = init_db(connect())
        try:
            conn.execute(
                "UPDATE memories SET trust_tier = 'verified', confidence = 0.9, last_verified_at = ?, evidence_hash = ? WHERE id = ?",
                (now_iso(), evidence_hash, memory_id_value),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id_value,)).fetchone()
            result = self._row(row) if row else None
            if result:
                result["provider_used"] = "sqlite"
            return result
        finally:
            conn.close()

    def supersede(self, old_memory_id: str, new_memory_id: str) -> None:
        conn = init_db(connect())
        try:
            conn.execute(
                "UPDATE memories SET superseded_by = ? WHERE id = ?",
                (new_memory_id, old_memory_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _claim_key(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))

    def apply_lifecycle_policy(
        self,
        workspace_id: str | None = None,
        agent_namespace: str = "default",
        hot_days: int | None = None,
        warm_days: int | None = None,
    ) -> dict[str, object]:
        if self._selected_hindsight():
            available, reason = self._hindsight.status()
            if available:
                try:
                    return self._hindsight.apply_lifecycle_policy(
                        workspace_id=workspace_id,
                        agent_namespace=agent_namespace,
                        hot_days=hot_days,
                        warm_days=warm_days,
                    )
                except ExternalHindsightUnavailable as exc:
                    reason = str(exc)
            data = self._apply_lifecycle_policy_sqlite(workspace_id, agent_namespace, hot_days, warm_days)
            data["provider_warning"] = self._fallback_warning(reason)
            data["provider_used"] = "sqlite_fallback"
            return data
        data = self._apply_lifecycle_policy_sqlite(workspace_id, agent_namespace, hot_days, warm_days)
        data["provider_used"] = "sqlite"
        return data

    def _retain_sqlite(
        self,
        claim: str,
        workspace_id: str | None = None,
        scope: str = "project",
        source: str = "user",
        files: list[str] | None = None,
        symbols: list[str] | None = None,
        docs: list[str] | None = None,
        confidence: float = 0.6,
        lifecycle_tier: str | None = None,
        agent_namespace: str = "default",
    ) -> dict[str, object]:
        workspace = get_workspace(workspace_id)
        wid = str(workspace["id"]) if workspace else "global"
        mid = memory_id(wid, claim, source)
        tier = self._normalize_tier(lifecycle_tier)
        namespace = (agent_namespace or "default").strip() or "default"
        evidence_hash = hashlib.sha256(
            stable_json({"claim": claim, "files": files or [], "symbols": symbols or [], "docs": docs or []}).encode("utf-8")
        ).hexdigest()
        conn = init_db(connect())
        try:
            summary = claim[:240]
            conn.execute(
                """
                INSERT OR REPLACE INTO memories(
                  id, workspace_id, session_id, scope, claim, summary, source, confidence,
                  trust_tier, linked_files_json, linked_symbols_json, linked_docs_json,
                  branch, created_at, last_verified_at, expires_at, superseded_by, evidence_hash,
                  lifecycle_tier, agent_namespace
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    wid,
                    os.environ.get("CTX_ENGINE_SESSION_ID", "local"),
                    scope,
                    claim,
                    summary,
                    source,
                    confidence,
                    "unverified",
                    json.dumps(files or [], ensure_ascii=False),
                    json.dumps(symbols or [], ensure_ascii=False),
                    json.dumps(docs or [], ensure_ascii=False),
                    os.environ.get("CTX_ENGINE_BRANCH"),
                    now_iso(),
                    None,
                    None,
                    None,
                    evidence_hash,
                    tier,
                    namespace,
                ),
            )
            conn.execute(
                "INSERT INTO memories_fts(memory_id, workspace_id, claim, summary, source) VALUES (?, ?, ?, ?, ?)",
                (mid, wid, claim, summary, source),
            )
            conn.commit()
            return {
                "id": mid,
                "workspace_id": wid,
                "claim": claim,
                "trust_tier": "unverified",
                "lifecycle_tier": tier,
                "agent_namespace": namespace,
            }
        finally:
            conn.close()

    def _recall_sqlite(
        self,
        query: str = "",
        workspace_id: str | None = None,
        scope: str = "project",
        limit: int = 10,
        agent_namespace: str = "default",
    ) -> list[dict[str, object]]:
        workspace = get_workspace(workspace_id)
        wid = str(workspace["id"]) if workspace else "global"
        namespace = (agent_namespace or "default").strip() or "default"
        conn = init_db(connect())
        try:
            if query:
                like = f"%{query}%"
                rows = conn.execute(
                    """
                    SELECT * FROM memories
                    WHERE workspace_id = ? AND scope = ? AND agent_namespace = ? AND superseded_by IS NULL
                      AND (claim LIKE ? OR summary LIKE ?)
                    ORDER BY last_verified_at DESC NULLS LAST, created_at DESC
                    LIMIT ?
                    """,
                    (wid, scope, namespace, like, like, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM memories
                    WHERE workspace_id = ? AND scope = ? AND agent_namespace = ? AND superseded_by IS NULL
                    ORDER BY last_verified_at DESC NULLS LAST, created_at DESC
                    LIMIT ?
                    """,
                    (wid, scope, namespace, limit),
                ).fetchall()
            return [self._row(row) for row in rows]
        finally:
            conn.close()

    def _apply_lifecycle_policy_sqlite(
        self,
        workspace_id: str | None = None,
        agent_namespace: str = "default",
        hot_days: int | None = None,
        warm_days: int | None = None,
    ) -> dict[str, object]:
        workspace = get_workspace(workspace_id)
        wid = str(workspace["id"]) if workspace else "global"
        namespace = (agent_namespace or "default").strip() or "default"
        hot = int(hot_days if hot_days is not None else os.environ.get("CTX_ENGINE_MEMORY_HOT_DAYS", "3"))
        warm = int(warm_days if warm_days is not None else os.environ.get("CTX_ENGINE_MEMORY_WARM_DAYS", "30"))
        if hot < 0 or warm < 0 or hot > warm:
            raise ValueError("memory lifecycle policy requires 0 <= hot_days <= warm_days")
        now = datetime.now(timezone.utc)
        hot_cutoff = now - timedelta(days=hot)
        warm_cutoff = now - timedelta(days=warm)

        conn = init_db(connect())
        try:
            rows = conn.execute(
                """
                SELECT id, created_at, last_verified_at
                FROM memories
                WHERE workspace_id = ? AND agent_namespace = ? AND superseded_by IS NULL
                """,
                (wid, namespace),
            ).fetchall()
            counts = {"hot": 0, "warm": 0, "cold": 0}
            updates: list[tuple[str, str]] = []
            for row in rows:
                stamp = str(row["last_verified_at"] or row["created_at"] or "")
                try:
                    dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                except Exception:
                    dt = now - timedelta(days=warm + 1)
                if dt >= hot_cutoff:
                    tier = "hot"
                elif dt >= warm_cutoff:
                    tier = "warm"
                else:
                    tier = "cold"
                counts[tier] += 1
                updates.append((tier, str(row["id"])))
            if updates:
                conn.executemany("UPDATE memories SET lifecycle_tier = ? WHERE id = ?", updates)
            conn.commit()
            return {
                "status": "ok",
                "workspace_id": wid,
                "agent_namespace": namespace,
                "policy": {"hot_days": hot, "warm_days": warm},
                "counts": counts,
                "updated": len(updates),
            }
        finally:
            conn.close()

    @staticmethod
    def _row(row) -> dict[str, object]:
        data = dict(row)
        data["linked_files"] = json.loads(data.pop("linked_files_json") or "[]")
        data["linked_symbols"] = json.loads(data.pop("linked_symbols_json") or "[]")
        data["linked_docs"] = json.loads(data.pop("linked_docs_json") or "[]")
        return data
