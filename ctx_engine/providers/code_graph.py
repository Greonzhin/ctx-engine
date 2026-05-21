from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..db import connect, init_db
from ..graph.indexer import RepositoryIndexer
from ..graph.skeletons import snippet_around
from ..security.redaction import redact_text
from ..workspace import get_workspace, get_workspace_for_path
from .build_test import BuildTestProvider
from .graph_store import build_graph_store

QUERY_STOPWORDS = {
    "where",
    "what",
    "which",
    "handled",
    "handle",
    "with",
    "the",
    "and",
    "for",
    "into",
    "from",
}

QUERY_SYNONYMS = {
    "auth": "authenticate",
    "authentication": "authenticate",
    "authorize": "authenticate",
    "authorization": "authenticate",
    "signin": "login",
    "sign-in": "login",
    "signup": "register",
}


class CodeGraphProvider:
    def __init__(self) -> None:
        self.graph_store = build_graph_store()

    def index_repository(self, path: str | Path) -> dict[str, object]:
        return RepositoryIndexer().index(path)

    def _resolve_workspace(self, workspace_id: str | None = None) -> dict[str, object] | None:
        if workspace_id:
            return get_workspace(workspace_id)
        local = get_workspace_for_path(os.getcwd())
        if local:
            return local
        return get_workspace()

    @staticmethod
    def _split_identifier(value: str) -> list[str]:
        parts: list[str] = []
        raw = value.replace("-", " ").replace(".", " ").replace("/", " ").replace("\\", " ")
        for chunk in raw.split():
            for piece in re.split(r"[_\s]+", chunk):
                if not piece:
                    continue
                camel = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", piece).split()
                parts.extend(camel if camel else [piece])
        return [item for item in parts if item]

    def _normalize_query_terms(self, query: str) -> list[str]:
        tokens = re.findall(r"[A-Za-z0-9_./\\-]+", query)
        normalized: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            for part in self._split_identifier(token):
                lowered = part.strip().lower()
                if len(lowered) <= 1 or lowered in QUERY_STOPWORDS:
                    continue
                canonical = QUERY_SYNONYMS.get(lowered, lowered)
                if canonical in seen:
                    continue
                seen.add(canonical)
                normalized.append(canonical)
        if not normalized:
            fallback = query.strip().lower()
            return [fallback] if fallback else []
        return normalized

    def _seed_symbols(self, query: str, workspace_id: str, limit: int) -> list[dict[str, object]]:
        base = self.search_symbols(query, workspace_id=workspace_id, limit=max(limit, 8))
        if len(base) >= limit:
            return base[:limit]
        terms = self._normalize_query_terms(query)
        expanded: list[dict[str, object]] = list(base)
        seen = {str(item.get("id")) for item in expanded if item.get("id")}
        for term in terms[:6]:
            rows = self.search_symbols(term, workspace_id=workspace_id, limit=max(4, limit // 2))
            for row in rows:
                rid = str(row.get("id"))
                if rid in seen:
                    continue
                seen.add(rid)
                expanded.append(row)
                if len(expanded) >= limit:
                    return expanded[:limit]
        return expanded[:limit]

    def search_symbols(
        self, query: str, workspace_id: str | None = None, limit: int = 20
    ) -> list[dict[str, object]]:
        workspace = self._resolve_workspace(workspace_id)
        if not workspace:
            return []
        wid = str(workspace["id"])
        terms = self._normalize_query_terms(query) or [query.strip().lower()]
        conn = init_db(connect())
        try:
            clauses = []
            params: list[object] = [wid]
            for term in terms:
                like = f"%{term}%"
                clauses.append("(lower(s.name) LIKE ? OR lower(s.signature) LIKE ? OR lower(f.rel_path) LIKE ?)")
                params.extend([like, like, like])
            params.append(limit * 4)
            rows = conn.execute(
                f"""
                SELECT s.*, f.rel_path, f.path, f.language, NULL AS bm25_rank
                FROM symbols s
                JOIN files f ON f.id = s.file_id
                WHERE s.workspace_id = ?
                  AND ({" OR ".join(clauses)})
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
            fts_query = " OR ".join(term for term in terms if term)
            fts_rows = []
            if fts_query:
                fts_rows = conn.execute(
                    """
                    SELECT s.*, f.rel_path, f.path, f.language, bm25(symbols_fts) AS bm25_rank
                    FROM symbols_fts x
                    JOIN symbols s ON s.id = x.symbol_id
                    JOIN files f ON f.id = s.file_id
                    WHERE x.workspace_id = ? AND symbols_fts MATCH ?
                    ORDER BY bm25(symbols_fts)
                    LIMIT ?
                    """,
                    (wid, fts_query, limit * 4),
                ).fetchall()
            merged = [self._symbol_row(row) for row in rows] + [self._symbol_row(row) for row in fts_rows]
            scored = self._rank_symbols(query, terms, merged)
            return scored[:limit]
        finally:
            conn.close()

    def get_file_skeleton(self, path: str, workspace_id: str | None = None) -> dict[str, object] | None:
        workspace = self._resolve_workspace(workspace_id)
        if not workspace:
            return None
        wid = str(workspace["id"])
        conn = init_db(connect())
        try:
            row = conn.execute(
                """
                SELECT rel_path, path, language, skeleton, sha256 FROM files
                WHERE workspace_id = ? AND (rel_path = ? OR path = ? OR rel_path LIKE ?)
                ORDER BY length(rel_path) LIMIT 1
                """,
                (wid, path, path, f"%{path}%"),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_symbol_context(self, symbol_name: str, workspace_id: str | None = None) -> dict[str, object] | None:
        matches = self.search_symbols(symbol_name, workspace_id, limit=1)
        if not matches:
            return None
        symbol = matches[0]
        file_path = Path(str(symbol["path"]))
        text = file_path.read_text(encoding="utf-8", errors="replace") if file_path.exists() else ""
        snippet = snippet_around(text, int(symbol["start_line"]), int(symbol["end_line"]))
        snippet["text"], redactions = redact_text(str(snippet["text"]))
        symbol["snippet"] = snippet
        symbol["redactions"] = redactions
        return symbol

    def get_symbol_references(
        self,
        symbol_name: str,
        workspace_id: str | None = None,
        depth: int = 1,
        limit: int = 30,
    ) -> dict[str, object]:
        workspace = self._resolve_workspace(workspace_id)
        if not workspace:
            return {"status": "ok", "workspace_id": None, "symbol_name": symbol_name, "references": []}
        wid = str(workspace["id"])
        seeds = self._seed_symbols(symbol_name, wid, limit=min(16, max(1, limit)))
        refs = self.graph_store.symbol_references(wid, seeds, depth=max(1, int(depth)), limit=max(1, int(limit)))
        return {
            "status": "ok",
            "workspace_id": wid,
            "symbol_name": symbol_name,
            "depth": max(1, int(depth)),
            "limit": max(1, int(limit)),
            "seeds": [
                {
                    "name": seed.get("name"),
                    "kind": seed.get("kind"),
                    "path": seed.get("rel_path"),
                    "semantic_confidence": seed.get("semantic_confidence", seed.get("confidence_label", "inferred")),
                    "edge_evidence": seed.get("edge_evidence", []),
                }
                for seed in seeds
            ],
            "backend": refs.get("backend"),
            "adapters": refs.get("adapters", []),
            "warning": refs.get("warning"),
            "references": refs.get("references", []),
        }

    def get_change_impact(
        self,
        query: str,
        workspace_id: str | None = None,
        depth: int = 1,
        limit: int = 30,
        include_tests: bool = True,
    ) -> dict[str, object]:
        workspace = self._resolve_workspace(workspace_id)
        if not workspace:
            return {"status": "ok", "workspace_id": None, "query": query, "impacted_files": []}
        wid = str(workspace["id"])
        seeds = self._seed_symbols(query, wid, limit=min(20, max(1, limit)))
        result = self.graph_store.change_impact(
            wid,
            query,
            seeds,
            root_path=str(workspace["root_path"]),
            depth=max(1, int(depth)),
            limit=max(1, int(limit)),
            include_tests=bool(include_tests),
        )
        result["workspace_id"] = wid
        return result

    def blast_radius(
        self,
        query: str,
        workspace_id: str | None = None,
        depth: int = 1,
        limit: int = 30,
    ) -> dict[str, object]:
        workspace = self._resolve_workspace(workspace_id)
        if not workspace:
            return {"status": "ok", "workspace_id": None, "query": query, "seeds": [], "related_files": [], "test_suggestions": []}
        wid = str(workspace["id"])
        root = Path(str(workspace["root_path"]))
        depth = max(1, min(int(depth), 2))
        limit = max(1, min(int(limit), 200))

        seeds = self._seed_symbols(query, wid, limit=min(24, limit))
        file_map: dict[str, dict[str, object]] = {}
        related_names: list[str] = []

        def add_file(symbol: dict[str, object], reason: str) -> None:
            path = str(symbol.get("rel_path") or symbol.get("path") or "")
            if not path:
                return
            current = file_map.get(path)
            if current is None:
                file_map[path] = {
                    "path": path,
                    "language": symbol.get("language"),
                    "reasons": [reason],
                    "confidence_label": symbol.get("confidence_label", "inferred"),
                    "semantic_confidence": symbol.get("semantic_confidence", symbol.get("confidence_label", "inferred")),
                    "edge_evidence": list(symbol.get("edge_evidence") or []),
                    "symbols": [symbol.get("name")],
                }
            else:
                if reason not in current["reasons"]:
                    current["reasons"].append(reason)
                if symbol.get("name") and symbol.get("name") not in current["symbols"]:
                    current["symbols"].append(symbol.get("name"))
                for evidence in list(symbol.get("edge_evidence") or []):
                    if evidence not in current["edge_evidence"]:
                        current["edge_evidence"].append(evidence)

        for seed in seeds:
            add_file(seed, "seed_match")
            for item in seed.get("imports", []) or []:
                for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", str(item)):
                    related_names.append(token)

        hops = 0
        visited_terms = set()
        frontier = [name for name in related_names if name not in visited_terms]
        while frontier and hops < depth:
            next_frontier: list[str] = []
            for name in frontier:
                visited_terms.add(name)
                rows = self.search_symbols(name, wid, limit=4)
                for row in rows:
                    add_file(row, "import_related")
                    if len(file_map) >= limit:
                        break
                if len(file_map) >= limit:
                    break
                for row in rows[:2]:
                    for item in row.get("imports", []) or []:
                        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", str(item)):
                            if token not in visited_terms:
                                next_frontier.append(token)
            frontier = next_frontier
            hops += 1
            if len(file_map) >= limit:
                break

        selected_files = list(file_map.keys())[:limit]
        test_suggestions = BuildTestProvider().detect(root, selected_files).get("suggested_tests", [])
        for test_path in test_suggestions:
            if test_path in file_map:
                if "linked_test" not in file_map[test_path]["reasons"]:
                    file_map[test_path]["reasons"].append("linked_test")
                continue
            if len(file_map) >= limit:
                break
            file_map[test_path] = {
                "path": test_path,
                "language": "test",
                "reasons": ["linked_test"],
                "confidence_label": "inferred",
                "semantic_confidence": "inferred",
                "edge_evidence": ["linked test file"],
                "symbols": [],
            }

        seeds_view = [
            {
                "name": row.get("name"),
                "kind": row.get("kind"),
                "path": row.get("rel_path"),
                "confidence_label": row.get("confidence_label", "inferred"),
                "semantic_confidence": row.get("semantic_confidence", row.get("confidence_label", "inferred")),
                "edge_evidence": row.get("edge_evidence", []),
                "retrieval_score": row.get("retrieval_score"),
            }
            for row in seeds
        ]
        related_files = sorted(file_map.values(), key=lambda item: (len(item["reasons"]), str(item["path"])), reverse=True)
        return {
            "status": "ok",
            "workspace_id": wid,
            "query": query,
            "depth": depth,
            "limit": limit,
            "seeds": seeds_view,
            "related_files": related_files[:limit],
            "test_suggestions": test_suggestions,
        }

    @staticmethod
    def _symbol_row(row) -> dict[str, object]:
        data = dict(row)
        data["imports"] = json.loads(data.pop("imports_json") or "[]")
        data["exports"] = json.loads(data.pop("exports_json") or "[]")
        data["route_like"] = bool(data["route_like"])
        data["test_name"] = bool(data["test_name"])
        return data

    @staticmethod
    def _semantic_for_row(query: str, terms: list[str], row: dict[str, object]) -> tuple[float, list[str]]:
        bonus = 0.0
        evidence: list[str] = []
        lowered_query = query.lower()
        semantic_mode = any(
            token in lowered_query
            for token in {"impact", "change", "reference", "references", "caller", "callee", "dependency", "blast"}
        )
        imports_text = "\n".join(str(item) for item in row.get("imports", []) or [])
        signature = str(row.get("signature", "")).lower()
        if semantic_mode:
            for term in terms:
                if term and term in imports_text.lower():
                    bonus += 6.0
                    evidence.append(f"import term:{term}")
                elif term and term in signature:
                    bonus += 2.0
                    evidence.append(f"signature term:{term}")
        if bool(row.get("test_name")) and any(token in lowered_query for token in {"test", "impact", "change", "regression"}):
            bonus += 6.0
            evidence.append("test_link")
        if bool(row.get("route_like")) and any(token in lowered_query for token in {"route", "endpoint", "api"}):
            bonus += 4.0
            evidence.append("route_reference")
        return bonus, evidence

    def _rank_symbols(self, query: str, terms: list[str], rows: list[dict[str, object]]) -> list[dict[str, object]]:
        want_route = any(token in query.lower() for token in {"route", "endpoint", "api"})
        want_test = any(token in query.lower() for token in {"test", "spec", "pytest"})
        dedup: dict[str, dict[str, object]] = {}

        for row in rows:
            name = str(row.get("name", ""))
            name_lower = name.lower()
            signature = str(row.get("signature", "")).lower()
            rel_path = str(row.get("rel_path", "")).lower()
            score = 0.0
            term_in_name = False
            term_in_signature = False
            term_in_path = False

            if name_lower == query.lower().strip():
                score += 100.0
            for term in terms:
                if term and term == name_lower:
                    score += 30.0
                    term_in_name = True
                elif term and term in name_lower:
                    score += 20.0
                    term_in_name = True
                if term and term in signature:
                    score += 8.0
                    term_in_signature = True
                if term and term in rel_path:
                    score += 5.0
                    term_in_path = True
            # Penalize path-only matches so exact/partial symbol matches stay ahead.
            if term_in_path and not term_in_name and not term_in_signature:
                score -= 6.0
            if bool(row.get("route_like")) and want_route:
                score += 6.0
            if bool(row.get("test_name")) and want_test:
                score += 6.0
            bm25_rank = row.get("bm25_rank")
            if isinstance(bm25_rank, (int, float)):
                score += min(20.0, max(0.0, float(-bm25_rank) * 5.0))

            semantic_bonus, edge_evidence = self._semantic_for_row(query, terms, row)
            score += semantic_bonus
            row["edge_evidence"] = sorted(set(edge_evidence))
            row["semantic_score"] = round(semantic_bonus, 4)

            row["retrieval_score"] = round(score, 4)
            if score >= 85:
                row["confidence_label"] = "extracted"
                row["semantic_confidence"] = "extracted"
            elif score >= 25:
                row["confidence_label"] = "inferred"
                row["semantic_confidence"] = "inferred"
            else:
                row["confidence_label"] = "ambiguous"
                row["semantic_confidence"] = "ambiguous"
            rid = str(row.get("id"))
            current = dedup.get(rid)
            if current is None or float(row["retrieval_score"]) > float(current.get("retrieval_score", 0.0)):
                dedup[rid] = row

        ordered = sorted(
            dedup.values(),
            key=lambda item: (
                float(item.get("retrieval_score", 0.0)),
                bool(item.get("route_like")),
                not bool(item.get("test_name")),
                -int(item.get("start_line") or 0),
            ),
            reverse=True,
        )
        return ordered
