from __future__ import annotations

from copy import deepcopy
from typing import Any


RECIPES: dict[str, dict[str, Any]] = {
    "fix-failing-test": {
        "name": "fix-failing-test",
        "intent": "debug_or_test",
        "steps": [
            "Read the failing test and nearest implementation context.",
            "Use capsule test_plan before broad test runs.",
            "Make the smallest behavior fix and rerun the targeted test.",
            "Run the project quality gate before handoff.",
        ],
        "recommended_commands": ["ctx capsule \"fix failing test\"", "pytest <targeted-test>", "pytest"],
        "required_context": ["selected_files", "selected_symbols", "build_test_context.test_plan", "exact_snippets"],
        "safety_notes": ["Do not weaken assertions to make tests pass.", "Keep secrets and ignored files out of context."],
    },
    "review-risky-change": {
        "name": "review-risky-change",
        "intent": "review",
        "steps": [
            "Inspect changed files and impacted symbols.",
            "Check blast radius and likely tests.",
            "Prioritize correctness, safety, and regression risk findings.",
        ],
        "recommended_commands": ["ctx semantic-impact \"review change\" --include-tests", "ctx mcp-lint --strict"],
        "required_context": ["selected_files", "selected_symbols", "build_test_context", "risks"],
        "safety_notes": ["Lead with concrete file/line findings.", "Do not review unrelated user changes as yours."],
    },
    "update-docs": {
        "name": "update-docs",
        "intent": "docs_lookup",
        "steps": [
            "Compare current docs with code and generated adapter behavior.",
            "Update only stale or contradictory documentation.",
            "Run docs scan and quality gate.",
        ],
        "recommended_commands": ["ctx docs-scan --strict", "ctx pack-summary \"documentation drift\""],
        "required_context": ["docs_context", "selected_files", "omitted_context"],
        "safety_notes": ["Do not paste private source into external docs providers.", "Keep source-of-truth notes explicit."],
    },
    "prepare-pr": {
        "name": "prepare-pr",
        "intent": "handoff",
        "steps": [
            "Summarize user-facing behavior changes.",
            "List verification commands and residual risks.",
            "Confirm CI status before final handoff.",
        ],
        "recommended_commands": ["git status --short --branch", "gh run list --limit 3"],
        "required_context": ["ledger_id", "build_test_context", "risks"],
        "safety_notes": ["Do not include secrets or local-only cache paths in summaries."],
    },
    "security-audit": {
        "name": "security-audit",
        "intent": "security",
        "steps": [
            "Run MCP descriptor and allowlist checks.",
            "Run optional scanners when installed.",
            "Inspect docs and egress reports for unsafe content.",
        ],
        "recommended_commands": ["ctx mcp-lint --strict", "ctx security-scan . --all", "ctx egress-report --provider context7"],
        "required_context": ["risks", "omitted_context", "provenance"],
        "safety_notes": ["Scanner adapters are optional unless strict mode is requested.", "No shell/write MCP tools are allowed."],
    },
}


def list_workflows() -> dict[str, Any]:
    recipes = [deepcopy(RECIPES[name]) for name in sorted(RECIPES)]
    return {"status": "ok", "recipes": recipes, "count": len(recipes)}


def show_workflow(name: str) -> dict[str, Any]:
    recipe = RECIPES.get(name)
    if not recipe:
        return {"status": "not_found", "name": name, "available": sorted(RECIPES)}
    result = deepcopy(recipe)
    result["status"] = "ok"
    return result


def suggest_workflow(query: str) -> dict[str, Any]:
    lower = query.lower()
    scores = {
        "fix-failing-test": _score(lower, ("test", "failing", "pytest", "spec", "auth", "bug", "fix")),
        "review-risky-change": _score(lower, ("review", "risk", "regression", "impact", "blast", "change")),
        "update-docs": _score(lower, ("docs", "documentation", "readme", "api", "adr", "guide")),
        "prepare-pr": _score(lower, ("pr", "pull request", "handoff", "release", "summary", "ci")),
        "security-audit": _score(lower, ("security", "audit", "secret", "mcp", "scanner", "semgrep", "gitleaks")),
    }
    selected = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0][0]
    if scores[selected] == 0:
        selected = "prepare-pr"
    recipe = deepcopy(RECIPES[selected])
    return {"status": "ok", "query": query, "selected": selected, "score": scores[selected], "recipe": recipe}


def _score(query: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if term in query)
