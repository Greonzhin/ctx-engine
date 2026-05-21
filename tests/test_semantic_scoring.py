from __future__ import annotations

from ctx_engine.providers.code_graph import CodeGraphProvider
from ctx_engine.providers.semantic import SemanticSourceRouter, SemanticSourceAdapter


def test_semantic_router_default_weight_order():
    assert SemanticSourceRouter._adapter_weight("lsp") > SemanticSourceRouter._adapter_weight("scip")


def test_semantic_router_confidence_weight_order():
    assert SemanticSourceRouter._confidence_weight("extracted") > SemanticSourceRouter._confidence_weight("inferred")
    assert SemanticSourceRouter._confidence_weight("inferred") > SemanticSourceRouter._confidence_weight("ambiguous")


def test_rank_symbols_exact_partial_path_only_order():
    provider = CodeGraphProvider()
    query = "authenticate_request"
    terms = ["authenticate_request"]
    rows = [
        {
            "id": "1",
            "name": "authenticate_request",
            "signature": "def authenticate_request(token):",
            "rel_path": "app/middleware.py",
            "start_line": 10,
            "imports": [],
            "route_like": False,
            "test_name": False,
            "bm25_rank": None,
        },
        {
            "id": "2",
            "name": "authenticate_request_v2",
            "signature": "def authenticate_request_v2(token):",
            "rel_path": "app/middleware_v2.py",
            "start_line": 12,
            "imports": [],
            "route_like": False,
            "test_name": False,
            "bm25_rank": None,
        },
        {
            "id": "3",
            "name": "handle_token",
            "signature": "def handle_token(token):",
            "rel_path": "legacy/authenticate_request_adapter.py",
            "start_line": 5,
            "imports": [],
            "route_like": False,
            "test_name": False,
            "bm25_rank": None,
        },
    ]
    ranked = provider._rank_symbols(query, terms, rows)
    names = [str(item.get("name")) for item in ranked]
    assert names.index("authenticate_request") < names.index("authenticate_request_v2")
    assert names.index("authenticate_request_v2") < names.index("handle_token")


def test_semantic_router_penalizes_non_seed_edges():
    class _Adapter(SemanticSourceAdapter):
        name = "lsp"

        def collect_edges(self, workspace_id, seeds, depth=1, limit=200):
            return {
                "adapter": self.name,
                "available": True,
                "warning": None,
                "edges": [
                    {
                        "from_symbol_id": "x1",
                        "from_symbol": "AuthMiddleware",
                        "from_path": "app/middleware.py",
                        "to_symbol_id": "seed-id",
                        "to_symbol": "authenticate_request",
                        "to_path": "app/middleware.py",
                        "edge_type": "reference",
                        "confidence": "extracted",
                        "evidence": "touching",
                    },
                    {
                        "from_symbol_id": "x2",
                        "from_symbol": "OtherSymbol",
                        "from_path": "app/other.py",
                        "to_symbol_id": "x3",
                        "to_symbol": "Third",
                        "to_path": "app/third.py",
                        "edge_type": "reference",
                        "confidence": "extracted",
                        "evidence": "non-touching",
                    },
                ],
            }

    router = SemanticSourceRouter()
    router.adapters = [_Adapter()]
    seeds = [{"id": "seed-id", "name": "authenticate_request"}]
    result = router.collect_edges("w", seeds, depth=1, limit=20)
    scores = {str(item.get("evidence")): float(item.get("semantic_score") or 0.0) for item in result.get("edges", [])}
    assert scores["touching"] > scores["non-touching"]
