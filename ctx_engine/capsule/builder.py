from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..db import now_iso
from ..graph.skeletons import snippet_around
from ..integrations.rtk import estimate_tokens, rank_text
from ..providers.action_ledger import ActionLedger
from ..providers.build_test import BuildTestProvider
from ..providers.cache import CacheProvider, capsule_namespace
from ..providers.capsule_feedback import CapsuleFeedbackProvider
from ..providers.code_graph import CodeGraphProvider
from ..providers.conventions import ConventionProvider
from ..providers.local_docs import LocalDocsProvider
from ..providers.memory import BuiltInMemoryProvider
from ..security.redaction import redact_text
from ..workflow import suggest_workflow
from ..workspace import get_workspace, workspace_fingerprint
from .budget import reserve_budget
from .conflicts import conflict_notes
from .provenance import provenance


class CapsuleBuilder:
    def __init__(self, mode: str = "safe") -> None:
        self.mode = mode
        self.code = CodeGraphProvider()
        self.docs = LocalDocsProvider()
        self.memory = BuiltInMemoryProvider()
        self.build_test = BuildTestProvider()
        self.conventions = ConventionProvider()
        self.feedback = CapsuleFeedbackProvider()
        self.ledger = ActionLedger()
        self.cache = CacheProvider()

    def build(
        self,
        query: str,
        token_budget: int = 4000,
        include_docs: bool = True,
        client_id: str = "generic",
        workspace_id: str | None = None,
    ) -> dict[str, object]:
        workspace = get_workspace(workspace_id)
        if not workspace:
            raise ValueError("No workspace is registered. Run `ctx index <path>` first.")
        wid = str(workspace["id"])
        root = Path(str(workspace["root_path"]))
        budget = reserve_budget(token_budget)
        index_fingerprint = workspace_fingerprint(wid)
        cache_key = {
            "workspace_id": wid,
            "index_fingerprint": index_fingerprint,
            "query": query,
            "token_budget": token_budget,
            "include_docs": include_docs,
            "mode": self.mode,
        }
        namespace = capsule_namespace(wid)
        cached = self.cache.get(namespace, cache_key)
        if cached:
            cached["cache"] = "hit"
            capsule_id = str(cached.get("provenance", {}).get("capsule_id") or "")
            if capsule_id:
                cached["feedback_context"] = self.feedback.summary(capsule_id, workspace_id=wid)
            return cached

        symbols = self.code.search_symbols(query, wid, limit=16)
        if not symbols:
            symbols = self._search_file_skeletons(query, wid, limit=8)
        selected_files = self._selected_files(symbols)
        skeletons = self._skeletons(selected_files, wid, query, budget["skeletons"])
        snippets = self._snippets(symbols, root, budget["snippets"])
        docs_context = self._docs(query, wid, budget["docs"]) if include_docs else []
        omitted_docs = self._omitted_docs(query, wid) if include_docs else []
        memory_context = self._memory(query, wid, budget["memory"])
        build_context = self.build_test.detect(root, [item["path"] for item in selected_files])
        workflow_context = suggest_workflow(query)
        project_conventions = self.conventions.summarize(workspace_id=wid, limit=5)

        capsule_id = hashlib.sha256(
            json.dumps(
                {"wid": wid, "query": query, "files": selected_files, "symbols": [s.get("id") for s in symbols]},
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:20]

        ledger_id = self.ledger.record(
            "capsule",
            f"capsule for {query[:80]}",
            {
                "capsule_id": capsule_id,
                "selected_files": [item["path"] for item in selected_files],
                "selected_symbols": [item.get("name") for item in symbols],
                "docs": [item.get("path") for item in docs_context],
                "memory_ids": [item.get("id") for item in memory_context],
                "mode": self.mode,
                "index_fingerprint": index_fingerprint,
                "cache": "miss",
            },
            client_id=client_id,
            workspace_id=wid,
        )

        capsule = {
            "task_brief": query,
            "intent": self._intent(query),
            "budget": {"requested": token_budget, "sections": budget},
            "client_id": client_id,
            "workspace_id": wid,
            "index_fingerprint": index_fingerprint,
            "selected_files": selected_files,
            "selected_symbols": [self._symbol_context(symbol) for symbol in symbols],
            "code_skeletons": skeletons,
            "exact_snippets": snippets,
            "docs_context": docs_context,
            "memory_context": memory_context,
            "build_test_context": build_context,
            "project_conventions": project_conventions,
            "workflow_context": workflow_context,
            "feedback_context": self.feedback.summary(capsule_id, workspace_id=wid),
            "risks": [
                "Sensitive and ignored paths are excluded before indexing.",
                "No shell or write tools are exposed by ctx-engine.",
            ],
            "test_suggestions": build_context.get("suggested_tests", []),
            "omitted_context": {
                "notes": ["Capsule uses ranked skeletons/snippets under budget.", f"mode={self.mode}"],
                "conflicts": conflict_notes(),
                "quarantined_docs": omitted_docs,
            },
            "provenance": {
                "capsule_id": capsule_id,
                "generated_at": now_iso(),
                "providers": [
                    "CodeGraphProvider",
                    "LocalDocsProvider",
                    "BuiltInMemoryProvider",
                    "BuildTestProvider",
                    "ConventionProvider",
                    "WorkflowProvider",
                    "CacheProvider",
                    "SafetyProvider",
                    "ActionLedger",
                ],
            },
            "ledger_id": ledger_id,
            "cache": "miss",
        }
        self.cache.set(namespace, cache_key, capsule)
        return capsule

    def _intent(self, query: str) -> str:
        lower = query.lower()
        if any(word in lower for word in ("test", "failing", "pytest", "spec")):
            return "debug_or_test"
        if any(word in lower for word in ("where", "handled", "find", "locate")):
            return "repo_navigation"
        if any(word in lower for word in ("docs", "api", "library")):
            return "docs_lookup"
        return "code_context"

    def _selected_files(self, symbols: list[dict[str, object]]) -> list[dict[str, object]]:
        seen: set[str] = set()
        items: list[dict[str, object]] = []
        for symbol in symbols:
            rel = str(symbol.get("rel_path") or symbol.get("path"))
            if rel in seen:
                continue
            seen.add(rel)
            items.append(
                {
                    "path": rel,
                    "language": symbol.get("language"),
                    "reason": f"matched symbol {symbol.get('name')}",
                    "confidence_label": symbol.get("confidence_label", "inferred"),
                    "semantic_confidence": symbol.get("semantic_confidence", symbol.get("confidence_label", "inferred")),
                    "edge_evidence": list(symbol.get("edge_evidence") or []),
                    "provenance": provenance(
                        "CodeGraphProvider",
                        rel,
                        symbol.get("start_line"),
                        trust_tier="local_code",
                        text=str(symbol.get("signature", "")),
                        confidence_label=str(symbol.get("confidence_label") or "inferred"),
                    ),
                }
            )
        return items

    def _skeletons(self, files: list[dict[str, object]], workspace_id: str, query: str, budget: int) -> list[dict[str, object]]:
        rows = []
        used = 0
        for item in files:
            skeleton = self.code.get_file_skeleton(str(item["path"]), workspace_id)
            if not skeleton:
                continue
            text = str(skeleton["skeleton"])
            tokens = estimate_tokens(text)
            if used + tokens > budget and rows:
                break
            used += tokens
            rows.append(
                {
                    "path": skeleton["rel_path"],
                    "language": skeleton["language"],
                    "skeleton": text,
                    "score": rank_text(query, text, str(skeleton["rel_path"])),
                    "provenance": provenance(
                        "CodeGraphProvider",
                        str(skeleton["rel_path"]),
                        "skeleton",
                        str(skeleton["sha256"]),
                        text=text,
                        confidence_label="extracted",
                    ),
                }
            )
        return sorted(rows, key=lambda item: item["score"], reverse=True)

    def _snippets(self, symbols: list[dict[str, object]], root: Path, budget: int) -> list[dict[str, object]]:
        snippets = []
        used = 0
        for symbol in symbols[:10]:
            path = Path(str(symbol["path"]))
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            snippet = snippet_around(text, int(symbol["start_line"]), int(symbol["end_line"]))
            body, redactions = redact_text(str(snippet["text"]))
            tokens = estimate_tokens(body)
            if used + tokens > budget and snippets:
                break
            used += tokens
            snippets.append(
                {
                    "path": str(symbol["rel_path"]),
                    "symbol": symbol["name"],
                    "start_line": snippet["start_line"],
                    "end_line": snippet["end_line"],
                    "text": body,
                    "redactions": redactions,
                    "provenance": provenance(
                        "CodeGraphProvider",
                        str(symbol["rel_path"]),
                        f"{snippet['start_line']}-{snippet['end_line']}",
                        symbol.get("id"),
                        text=body,
                        confidence_label=str(symbol.get("confidence_label") or "extracted"),
                    ),
                }
            )
        return snippets

    def _docs(self, query: str, workspace_id: str, budget: int) -> list[dict[str, object]]:
        docs = []
        used = 0
        for row in self.docs.query(query, workspace_id, limit=6, include_quarantined=False):
            body = str(row["body"])
            tokens = estimate_tokens(body)
            if used + tokens > budget and docs:
                break
            used += tokens
            docs.append(
                {
                    "path": row["rel_path"],
                    "title": row["title"],
                    "text": body,
                    "confidence_label": "extracted",
                    "provenance": provenance(
                        "LocalDocsProvider",
                        str(row["rel_path"]),
                        "section",
                        str(row["sha256"]),
                        trust_tier="local_docs",
                        text=body,
                        confidence_label="extracted",
                    ),
                }
            )
        return docs

    def _omitted_docs(self, query: str, workspace_id: str) -> list[dict[str, object]]:
        omitted: list[dict[str, object]] = []
        for row in self.docs.query(query, workspace_id, limit=10, include_quarantined=True):
            if not bool(row.get("quarantined")):
                continue
            omitted.append(
                {
                    "path": row.get("rel_path"),
                    "reason": "quarantined_high_risk_doc",
                    "risk_level": row.get("risk_level"),
                    "risk_flags": row.get("risk_flags", []),
                }
            )
        return omitted

    def _memory(self, query: str, workspace_id: str, budget: int) -> list[dict[str, object]]:
        items = []
        used = 0
        for memory in self.memory.recall(query, workspace_id, limit=8):
            text = str(memory["summary"])
            tokens = estimate_tokens(text)
            if used + tokens > budget and items:
                break
            used += tokens
            items.append(memory)
        return items

    def _symbol_context(self, symbol: dict[str, object]) -> dict[str, object]:
        return {
            "name": symbol.get("name"),
            "kind": symbol.get("kind"),
            "signature": symbol.get("signature"),
            "path": symbol.get("rel_path"),
            "start_line": symbol.get("start_line"),
            "end_line": symbol.get("end_line"),
            "route_like": symbol.get("route_like"),
            "test_name": symbol.get("test_name"),
            "semantic_confidence": symbol.get("semantic_confidence", symbol.get("confidence_label", "inferred")),
            "edge_evidence": list(symbol.get("edge_evidence") or []),
            "provenance": provenance(
                "CodeGraphProvider",
                str(symbol.get("rel_path")),
                symbol.get("start_line"),
                symbol.get("id"),
                text=str(symbol.get("signature", "")),
                confidence_label=str(symbol.get("confidence_label") or "inferred"),
            ),
            "confidence_label": symbol.get("confidence_label", "inferred"),
        }

    def _search_file_skeletons(self, query: str, workspace_id: str, limit: int) -> list[dict[str, object]]:
        from ..db import connect, init_db

        conn = init_db(connect())
        like = f"%{query}%"
        try:
            rows = conn.execute(
                """
                SELECT id, workspace_id, id AS file_id, rel_path, path, language,
                       rel_path AS name, 'file' AS kind, skeleton AS signature,
                       1 AS start_line, 1 AS end_line, 0 AS route_like, 0 AS test_name,
                       '[]' AS imports_json, '[]' AS exports_json
                FROM files
                WHERE workspace_id = ? AND (rel_path LIKE ? OR skeleton LIKE ?)
                LIMIT ?
                """,
                (workspace_id, like, like, limit),
            ).fetchall()
            items = [dict(row) for row in rows]
            for item in items:
                item["confidence_label"] = "ambiguous"
            return items
        finally:
            conn.close()
