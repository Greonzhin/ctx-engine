from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .build_test import BuildTestProvider
from .semantic import SemanticSourceRouter


class SQLiteGraphStore:
    backend_name = "sqlite"

    def __init__(self) -> None:
        self.semantic = SemanticSourceRouter()

    def symbol_references(
        self,
        workspace_id: str,
        seeds: list[dict[str, object]],
        depth: int = 1,
        limit: int = 30,
    ) -> dict[str, object]:
        semantic = self.semantic.collect_edges(workspace_id, seeds, depth=depth, limit=max(limit * 8, 40))
        references = self._references_from_edges(semantic.get("edges", []), seeds, limit=limit)
        return {
            "status": "ok",
            "backend": self.backend_name,
            "adapters": semantic.get("adapters", []),
            "references": references,
        }

    @staticmethod
    def _references_from_edges(edges: list[dict[str, object]], seeds: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
        seed_ids = {str(item.get("id")) for item in seeds if item.get("id")}
        seed_names = {str(item.get("name") or "") for item in seeds if str(item.get("name") or "")}
        references: list[dict[str, object]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for edge in edges:
            from_id = str(edge.get("from_symbol_id"))
            to_id = str(edge.get("to_symbol_id"))
            from_name = str(edge.get("from_symbol") or "")
            to_name = str(edge.get("to_symbol") or "")
            touches_seed = (
                from_id in seed_ids
                or to_id in seed_ids
                or from_name in seed_names
                or to_name in seed_names
            )
            if not touches_seed:
                continue
            if to_id in seed_ids or to_name in seed_names:
                symbol_name = edge.get("from_symbol")
                symbol_path = edge.get("from_path")
                symbol_kind = edge.get("from_kind")
                target_name = edge.get("to_symbol")
            else:
                symbol_name = edge.get("to_symbol")
                symbol_path = edge.get("to_path")
                symbol_kind = edge.get("to_kind")
                target_name = edge.get("from_symbol")
            key = (
                str(symbol_name),
                str(symbol_path),
                str(target_name),
                str(edge.get("edge_type")),
            )
            if key in seen:
                continue
            seen.add(key)
            references.append(
                {
                    "symbol": symbol_name,
                    "kind": symbol_kind,
                    "path": symbol_path,
                    "target_symbol": target_name,
                    "edge_type": edge.get("edge_type"),
                    "evidence": edge.get("evidence"),
                    "semantic_confidence": edge.get("confidence", "inferred"),
                    "semantic_score": edge.get("semantic_score"),
                    "edge_evidence": [edge.get("evidence")],
                }
            )
            if len(references) >= limit:
                break
        return references

    def change_impact(
        self,
        workspace_id: str,
        query: str,
        seeds: list[dict[str, object]],
        root_path: str | Path,
        depth: int = 1,
        limit: int = 30,
        include_tests: bool = True,
    ) -> dict[str, object]:
        ref_result = self.symbol_references(workspace_id, seeds, depth=depth, limit=max(limit * 4, 30))
        impacted: dict[str, dict[str, object]] = {}

        def add_file(path: str, reason: str, confidence: str, symbol: str | None = None, evidence: str | None = None) -> None:
            if not path:
                return
            row = impacted.get(path)
            if row is None:
                row = {
                    "path": path,
                    "reasons": [reason],
                    "semantic_confidence": confidence,
                    "edge_evidence": [evidence] if evidence else [],
                    "symbols": [symbol] if symbol else [],
                }
                impacted[path] = row
                return
            if reason not in row["reasons"]:
                row["reasons"].append(reason)
            if evidence and evidence not in row["edge_evidence"]:
                row["edge_evidence"].append(evidence)
            if symbol and symbol not in row["symbols"]:
                row["symbols"].append(symbol)
            if confidence == "extracted":
                row["semantic_confidence"] = "extracted"
            elif confidence == "inferred" and row["semantic_confidence"] == "ambiguous":
                row["semantic_confidence"] = "inferred"

        for seed in seeds:
            add_file(
                str(seed.get("rel_path") or seed.get("path") or ""),
                "seed_match",
                str(seed.get("semantic_confidence") or seed.get("confidence_label") or "inferred"),
                symbol=str(seed.get("name") or ""),
                evidence="seed symbol",
            )

        for ref in ref_result.get("references", []):
            path = str(ref.get("path") or "")
            edge_type = str(ref.get("edge_type") or "reference")
            if not include_tests and edge_type == "test_link":
                continue
            if not include_tests and "/test" in path.replace("\\", "/"):
                continue
            add_file(
                path,
                edge_type,
                str(ref.get("semantic_confidence") or "inferred"),
                symbol=str(ref.get("symbol") or ""),
                evidence=str(ref.get("evidence") or ""),
            )

        suggested_tests = BuildTestProvider().detect(Path(root_path), list(impacted.keys())).get("suggested_tests", [])
        if include_tests:
            for test_path in suggested_tests:
                add_file(
                    str(test_path),
                    "suggested_test",
                    "inferred",
                    symbol=None,
                    evidence="build-test suggestion",
                )
        ordered = sorted(impacted.values(), key=lambda item: (len(item["reasons"]), str(item["path"])), reverse=True)
        return {
            "status": "ok",
            "backend": self.backend_name,
            "adapters": ref_result.get("adapters", []),
            "query": query,
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
            "impacted_files": ordered[:limit],
            "suggested_tests": suggested_tests if include_tests else [],
        }


class KuzuGraphStore(SQLiteGraphStore):
    backend_name = "kuzu"

    def __init__(self) -> None:
        super().__init__()
        self._available, self._warning = self._detect()
        self._kuzu = None
        if self._available:
            try:
                import kuzu as _kuzu  # type: ignore

                self._kuzu = _kuzu
            except Exception:
                self._available = False
                self._warning = "Kuzu backend is selected but kuzu package failed to import; using sqlite fallback."

    @staticmethod
    def _detect() -> tuple[bool, str | None]:
        value = (os.environ.get("CTX_ENGINE_GRAPH_BACKEND", "sqlite") or "sqlite").strip().lower()
        if value != "kuzu":
            return False, "Kuzu backend is not selected."
        try:
            import kuzu  # noqa: F401

            return True, None
        except Exception:
            return False, "Kuzu backend is selected but kuzu package is unavailable; using sqlite fallback."

    def symbol_references(
        self,
        workspace_id: str,
        seeds: list[dict[str, object]],
        depth: int = 1,
        limit: int = 30,
    ) -> dict[str, object]:
        semantic = self.semantic.collect_edges(workspace_id, seeds, depth=depth, limit=max(limit * 8, 40))
        if not self._available or self._kuzu is None:
            result = {
                "status": "ok",
                "backend": "sqlite_fallback",
                "adapters": semantic.get("adapters", []),
                "references": self._references_from_edges(semantic.get("edges", []), seeds, limit=limit),
            }
            if self._warning:
                result["warning"] = self._warning
            return result
        try:
            kuzu_edges = self._kuzu_ranked_edges(semantic.get("edges", []), seeds, limit=max(limit * 8, 40))
            references = self._references_from_edges(kuzu_edges, seeds, limit=limit)
            return {
                "status": "ok",
                "backend": "kuzu",
                "adapters": semantic.get("adapters", []),
                "references": references,
            }
        except Exception as exc:
            fallback = {
                "status": "ok",
                "backend": "sqlite_fallback",
                "adapters": semantic.get("adapters", []),
                "references": self._references_from_edges(semantic.get("edges", []), seeds, limit=limit),
                "warning": f"Kuzu runtime query failed ({exc}); using sqlite fallback.",
            }
            return fallback

    def change_impact(
        self,
        workspace_id: str,
        query: str,
        seeds: list[dict[str, object]],
        root_path: str | Path,
        depth: int = 1,
        limit: int = 30,
        include_tests: bool = True,
    ) -> dict[str, object]:
        result = super().change_impact(
            workspace_id,
            query,
            seeds,
            root_path,
            depth=depth,
            limit=limit,
            include_tests=include_tests,
        )
        result["backend"] = "kuzu" if self._available else "sqlite_fallback"
        if self._warning:
            result["warning"] = self._warning
        return result

    @staticmethod
    def _q(value: object) -> str:
        text = str(value or "")
        return "'" + text.replace("\\", "\\\\").replace("'", "''") + "'"

    @staticmethod
    def _rows_from_result(result: object) -> list[dict[str, object]]:
        if result is None:
            return []
        # kuzu python wrapper can expose rows_as_dict/get_all.
        rows_as_dict = getattr(result, "rows_as_dict", None)
        if callable(rows_as_dict):
            try:
                obj = rows_as_dict()
                get_all = getattr(obj, "get_all", None)
                if callable(get_all):
                    rows = get_all()
                    if isinstance(rows, list):
                        return [item for item in rows if isinstance(item, dict)]
            except Exception:
                pass
        get_all = getattr(result, "get_all", None)
        if callable(get_all):
            try:
                rows = get_all()
                if isinstance(rows, list):
                    normalized: list[dict[str, object]] = []
                    for item in rows:
                        if isinstance(item, dict):
                            normalized.append(item)
                    if normalized:
                        return normalized
            except Exception:
                pass
        has_next = getattr(result, "has_next", None)
        get_next = getattr(result, "get_next", None)
        if callable(has_next) and callable(get_next):
            out: list[dict[str, object]] = []
            try:
                while bool(has_next()):
                    item = get_next()
                    if isinstance(item, dict):
                        out.append(item)
            except Exception:
                return out
            return out
        return []

    def _kuzu_ranked_edges(
        self,
        edges: list[dict[str, object]],
        seeds: list[dict[str, object]],
        limit: int,
    ) -> list[dict[str, object]]:
        db_dir = Path(tempfile.mkdtemp(prefix="ctx_engine_kuzu_"))
        db = self._kuzu.Database(str(db_dir))  # type: ignore[union-attr]
        conn = self._kuzu.Connection(db)  # type: ignore[union-attr]
        conn.execute("CREATE NODE TABLE IF NOT EXISTS Symbol(id STRING PRIMARY KEY, name STRING, path STRING, kind STRING, is_test BOOLEAN);")
        conn.execute("CREATE REL TABLE IF NOT EXISTS Edge(FROM Symbol TO Symbol, edge_type STRING, evidence STRING, confidence STRING, score DOUBLE);")

        node_map: dict[str, dict[str, object]] = {}
        for edge in edges:
            from_id = str(edge.get("from_symbol_id") or f"anon:{edge.get('from_symbol')}:{edge.get('from_path')}")
            to_id = str(edge.get("to_symbol_id") or f"anon:{edge.get('to_symbol')}:{edge.get('to_path')}")
            if from_id not in node_map:
                node_map[from_id] = {
                    "id": from_id,
                    "name": str(edge.get("from_symbol") or ""),
                    "path": str(edge.get("from_path") or ""),
                    "kind": str(edge.get("from_kind") or ""),
                    "test": bool(edge.get("from_test_name")),
                }
            if to_id not in node_map:
                node_map[to_id] = {
                    "id": to_id,
                    "name": str(edge.get("to_symbol") or ""),
                    "path": str(edge.get("to_path") or ""),
                    "kind": str(edge.get("to_kind") or ""),
                    "test": bool(edge.get("to_test_name")),
                }
            edge["_norm_from_id"] = from_id
            edge["_norm_to_id"] = to_id

        for node in node_map.values():
            conn.execute(
                "CREATE (:Symbol {id: %s, name: %s, path: %s, kind: %s, is_test: %s});"
                % (
                    self._q(node["id"]),
                    self._q(node["name"]),
                    self._q(node["path"]),
                    self._q(node["kind"]),
                    "true" if bool(node["test"]) else "false",
                )
            )

        for edge in edges:
            conn.execute(
                "MATCH (a:Symbol {id: %s}), (b:Symbol {id: %s}) CREATE (a)-[:Edge {edge_type: %s, evidence: %s, confidence: %s, score: %s}]->(b);"
                % (
                    self._q(edge.get("_norm_from_id")),
                    self._q(edge.get("_norm_to_id")),
                    self._q(edge.get("edge_type") or "reference"),
                    self._q(edge.get("evidence") or ""),
                    self._q(edge.get("confidence") or "inferred"),
                    str(float(edge.get("semantic_score") or 0.0)),
                )
            )

        seed_ids = []
        for seed in seeds:
            sid = str(seed.get("id") or "")
            if sid:
                seed_ids.append(self._q(sid))
        if not seed_ids:
            return edges[:limit]
        query = (
            "MATCH (a:Symbol)-[e:Edge]->(b:Symbol) "
            f"WHERE a.id IN [{', '.join(seed_ids)}] OR b.id IN [{', '.join(seed_ids)}] "
            "RETURN a.id AS from_id, a.name AS from_name, a.path AS from_path, a.kind AS from_kind, a.is_test AS from_test, "
            "b.id AS to_id, b.name AS to_name, b.path AS to_path, b.kind AS to_kind, b.is_test AS to_test, "
            "e.edge_type AS edge_type, e.evidence AS evidence, e.confidence AS confidence, e.score AS score "
            "ORDER BY e.score DESC "
            f"LIMIT {max(1, int(limit))};"
        )
        rows = self._rows_from_result(conn.execute(query))
        if not rows:
            return edges[:limit]
        ranked: list[dict[str, object]] = []
        for row in rows:
            ranked.append(
                {
                    "from_symbol_id": row.get("from_id"),
                    "from_symbol": row.get("from_name"),
                    "from_path": row.get("from_path"),
                    "from_kind": row.get("from_kind"),
                    "from_test_name": bool(row.get("from_test")),
                    "to_symbol_id": row.get("to_id"),
                    "to_symbol": row.get("to_name"),
                    "to_path": row.get("to_path"),
                    "to_kind": row.get("to_kind"),
                    "to_test_name": bool(row.get("to_test")),
                    "edge_type": row.get("edge_type"),
                    "evidence": row.get("evidence"),
                    "confidence": row.get("confidence"),
                    "semantic_score": row.get("score"),
                    "source_adapter": "kuzu",
                }
            )
        return ranked


def build_graph_store() -> SQLiteGraphStore:
    backend = (os.environ.get("CTX_ENGINE_GRAPH_BACKEND", "sqlite") or "sqlite").strip().lower()
    if backend == "kuzu":
        return KuzuGraphStore()
    return SQLiteGraphStore()
