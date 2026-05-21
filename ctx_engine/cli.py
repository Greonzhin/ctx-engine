from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .benchmark import benchmark_capsule
from .capsule.builder import CapsuleBuilder
from .client_check import check_clients
from .client_adapters import ClaudeAdapter, CodexAdapter, GeminiAdapter, GenericAdapter
from .config import DEFAULT_HOST, DEFAULT_PORT, SUPPORTED_MODES, ensure_project_config
from .doctor import doctor_status
from .inspector_smoke import inspector_smoke
from .mcp_contract import check_gateway_contract, check_http_gateway_contract
from .mcp_lint import lint_gateway_tools
from .pathmap import check_paths, map_path
from .providers.action_ledger import ActionLedger
from .providers.code_graph import CodeGraphProvider
from .providers.egress import EgressProvider
from .providers.context7_docs import Context7DocsProvider
from .providers.local_docs import LocalDocsProvider
from .providers.memory import BuiltInMemoryProvider
from .pack_summary import pack_summary
from .retrieval_benchmark import run_retrieval_benchmark
from .server import serve
from .workspace import get_workspace, list_workspaces, register_workspace


def client_adapters() -> dict[str, object]:
    return {
        "codex": CodexAdapter(),
        "claude": ClaudeAdapter(),
        "gemini": GeminiAdapter(),
        "generic": GenericAdapter(),
    }


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    written = ensure_project_config(root)
    register_workspace(root)
    print_json({"status": "ok", "workspace": str(root), "written": [str(path) for path in written]})
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    ensure_project_config(root)
    code_result = CodeGraphProvider().index_repository(root)
    docs_result = LocalDocsProvider().index(code_result["root_path"], str(code_result["workspace_id"]))
    ActionLedger().record(
        "index",
        f"indexed {root}",
        {"code": code_result, "docs": docs_result},
        client_id="cli",
        workspace_id=str(code_result["workspace_id"]),
    )
    print_json({"code": code_result, "local_docs": docs_result})
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    workspaces = list_workspaces()
    print_json({"workspaces": workspaces, "default_workspace": get_workspace()})
    return 0


def cmd_capsule(args: argparse.Namespace) -> int:
    capsule = CapsuleBuilder(mode=args.mode).build(
        args.query,
        token_budget=args.token_budget,
        include_docs=not args.no_docs,
        client_id=args.client_id,
        workspace_id=args.workspace_id,
    )
    if args.markdown:
        print(f"# Context Capsule\n\nTask: {capsule['task_brief']}\n")
        print("## Files")
        for item in capsule["selected_files"]:
            print(f"- {item['path']} - {item['reason']}")
        print("\n## Suggested Tests")
        for item in capsule["test_suggestions"]:
            print(f"- {item}")
        print(f"\nLedger: {capsule['ledger_id']}")
    else:
        print_json(capsule)
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    provider = Context7DocsProvider(mode=args.mode)
    if args.docs_command == "resolve":
        print_json(provider.resolve(args.query))
    elif args.docs_command == "query":
        print_json(provider.query(args.library_id, args.query))
    else:
        raise SystemExit("unknown docs command")
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    provider = BuiltInMemoryProvider()
    if args.memory_command == "add":
        print_json(
            provider.retain(
                args.claim,
                lifecycle_tier=getattr(args, "lifecycle_tier", None),
                agent_namespace=getattr(args, "agent_namespace", "default"),
            )
        )
    elif args.memory_command == "search":
        print_json(provider.recall(args.query, agent_namespace=getattr(args, "agent_namespace", "default")))
    elif args.memory_command == "policy":
        print_json(
            provider.apply_lifecycle_policy(
                workspace_id=getattr(args, "workspace_id", None),
                agent_namespace=getattr(args, "agent_namespace", "default"),
                hot_days=getattr(args, "hot_days", None),
                warm_days=getattr(args, "warm_days", None),
            )
        )
    else:
        raise SystemExit("unknown memory command")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    adapters = client_adapters()
    root = Path(args.path).resolve()
    if args.client == "status":
        selected = {args.adapter: adapters[args.adapter]} if args.adapter else adapters
        statuses = {client_id: adapter.status(root) for client_id, adapter in selected.items()}
        print_json(
            {
                "status": "ok",
                "workspace_path": str(root),
                "all_installed": all(bool(item["installed"]) for item in statuses.values()),
                "clients": statuses,
            }
        )
        return 0
    adapter = adapters[args.client]
    result = adapter.install(root)
    ActionLedger().record("install", f"installed {args.client} adapter", result.__dict__, client_id="cli")
    print_json(result.__dict__)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    result = doctor_status(args.path)
    print_json(result)
    if args.strict:
        return 0 if result["status"] == "healthy" and not result.get("warnings") else 1
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    if args.path_command == "check":
        print_json(check_paths(args.path))
    elif args.path_command == "map":
        print_json(map_path(args.path))
    else:
        raise SystemExit("unknown path command")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    serve(args.host, args.port, args.mode)
    return 0


def cmd_mcp_check(args: argparse.Namespace) -> int:
    if args.endpoint:
        result = check_http_gateway_contract(args.endpoint, timeout=args.timeout)
    else:
        result = check_gateway_contract(args.mode)
    print_json(result)
    return 0 if result["status"] == "pass" else 1


def cmd_mcp_lint(args: argparse.Namespace) -> int:
    result = lint_gateway_tools(args.mode)
    print_json(result)
    if args.strict:
        return 0 if result["status"] == "pass" else 1
    return 0


def cmd_inspector_smoke(args: argparse.Namespace) -> int:
    result = inspector_smoke(endpoint=args.endpoint, run=args.run, timeout=args.timeout)
    print_json(result)
    if args.strict:
        return 0 if result["status"] == "pass" else 1
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    result = benchmark_capsule(
        args.query,
        path=args.path,
        workspace_id=args.workspace_id,
        token_budget=args.token_budget,
        include_docs=not args.no_docs,
        mode=args.mode,
        reindex=args.reindex,
    )
    print_json(result)
    return 0


def cmd_docs_scan(args: argparse.Namespace) -> int:
    workspace = get_workspace(args.workspace_id)
    if not workspace:
        raise ValueError("No workspace is registered. Run `ctx index <path>` first.")
    result = LocalDocsProvider().risk_summary(str(workspace["id"]), limit=args.limit)
    print_json(result)
    return 1 if args.strict and int(result["risk_counts"]["high"]) > 0 else 0


def cmd_egress_report(args: argparse.Namespace) -> int:
    result = EgressProvider().report(since=args.since, limit=args.limit, provider=args.provider)
    print_json(result)
    return 0


def cmd_pack_summary(args: argparse.Namespace) -> int:
    result = pack_summary(
        args.query,
        workspace_id=args.workspace_id,
        token_budget=args.token_budget,
        max_files=args.max_files,
        include_docs=not args.no_docs,
    )
    print_json(result)
    return 0


def cmd_blast_radius(args: argparse.Namespace) -> int:
    result = CodeGraphProvider().blast_radius(
        args.query,
        workspace_id=args.workspace_id,
        depth=args.depth,
        limit=args.limit,
    )
    print_json(result)
    return 0


def cmd_semantic_refs(args: argparse.Namespace) -> int:
    result = CodeGraphProvider().get_symbol_references(
        args.symbol_name,
        workspace_id=args.workspace_id,
        depth=args.depth,
        limit=args.limit,
    )
    print_json(result)
    return 0


def cmd_semantic_impact(args: argparse.Namespace) -> int:
    result = CodeGraphProvider().get_change_impact(
        args.query,
        workspace_id=args.workspace_id,
        depth=args.depth,
        limit=args.limit,
        include_tests=args.include_tests,
    )
    print_json(result)
    return 0


def cmd_retrieval_benchmark(args: argparse.Namespace) -> int:
    result = run_retrieval_benchmark(
        path=args.path,
        workspace_id=args.workspace_id,
        cases_file=args.cases_file,
        top_k=args.top_k,
    )
    print_json(result)
    return 0


def cmd_client_check(args: argparse.Namespace) -> int:
    result = check_clients(args.path, adapter=args.adapter, run=args.run, timeout=args.timeout)
    print_json(result)
    return 1 if args.strict and result["status"] != "ok" else 0


def cmd_ledger(args: argparse.Namespace) -> int:
    ledger = ActionLedger()
    if args.ledger_command == "tail":
        print_json(ledger.tail(limit=args.limit, query=args.query or ""))
    elif args.ledger_command == "show":
        print_json(ledger.show(args.id))
    elif args.ledger_command == "export":
        print_json(ledger.export())
    else:
        raise SystemExit("unknown ledger command")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctx", description="ctx-engine local MCP context gateway")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("path", nargs="?", default=".")
    init.set_defaults(func=cmd_init)

    index = sub.add_parser("index")
    index.add_argument("path")
    index.set_defaults(func=cmd_index)

    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)

    capsule = sub.add_parser("capsule")
    capsule.add_argument("query")
    capsule.add_argument("--token-budget", type=int, default=4000)
    capsule.add_argument("--workspace-id")
    capsule.add_argument("--client-id", default="cli")
    capsule.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default="safe")
    capsule.add_argument("--no-docs", action="store_true")
    capsule.add_argument("--markdown", action="store_true")
    capsule.set_defaults(func=cmd_capsule)

    docs = sub.add_parser("docs")
    docs.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default="safe")
    docs_sub = docs.add_subparsers(dest="docs_command", required=True)
    docs_resolve = docs_sub.add_parser("resolve")
    docs_resolve.add_argument("query")
    docs_resolve.set_defaults(func=cmd_docs)
    docs_query = docs_sub.add_parser("query")
    docs_query.add_argument("library_id")
    docs_query.add_argument("query")
    docs_query.set_defaults(func=cmd_docs)

    memory = sub.add_parser("memory")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    memory_add = memory_sub.add_parser("add")
    memory_add.add_argument("claim")
    memory_add.add_argument("--lifecycle-tier", choices=["hot", "warm", "cold"])
    memory_add.add_argument("--agent-namespace", default="default")
    memory_add.set_defaults(func=cmd_memory)
    memory_search = memory_sub.add_parser("search")
    memory_search.add_argument("query", nargs="?", default="")
    memory_search.add_argument("--agent-namespace", default="default")
    memory_search.set_defaults(func=cmd_memory)
    memory_policy = memory_sub.add_parser("policy")
    memory_policy.add_argument("--workspace-id")
    memory_policy.add_argument("--agent-namespace", default="default")
    memory_policy.add_argument("--hot-days", type=int)
    memory_policy.add_argument("--warm-days", type=int)
    memory_policy.set_defaults(func=cmd_memory)

    install = sub.add_parser("install")
    install.add_argument("client", choices=["codex", "claude", "gemini", "generic", "status"])
    install.add_argument("path", nargs="?", default=".")
    install.add_argument("--adapter", choices=["codex", "claude", "gemini", "generic"])
    install.set_defaults(func=cmd_install)

    doctor = sub.add_parser("doctor")
    doctor.add_argument("path", nargs="?", default=".")
    doctor.add_argument("--strict", action="store_true", help="Return non-zero when doctor reports warnings or unhealthy status.")
    doctor.set_defaults(func=cmd_doctor)

    path = sub.add_parser("path")
    path_sub = path.add_subparsers(dest="path_command", required=True)
    path_check = path_sub.add_parser("check")
    path_check.add_argument("path", nargs="?", default=None)
    path_check.set_defaults(func=cmd_path)
    path_map = path_sub.add_parser("map")
    path_map.add_argument("path")
    path_map.set_defaults(func=cmd_path)

    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default=DEFAULT_HOST)
    serve_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_parser.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default="safe")
    serve_parser.set_defaults(func=cmd_serve)

    mcp = sub.add_parser("mcp")
    mcp.add_argument("--host", default=DEFAULT_HOST)
    mcp.add_argument("--port", type=int, default=DEFAULT_PORT)
    mcp.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default="safe")
    mcp.set_defaults(func=cmd_serve)

    mcp_check = sub.add_parser("mcp-check")
    mcp_check.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default="safe")
    mcp_check.add_argument("--endpoint", help="Check a running streamable HTTP MCP endpoint instead of the in-process gateway.")
    mcp_check.add_argument("--timeout", type=float, default=2.0)
    mcp_check.set_defaults(func=cmd_mcp_check)

    mcp_lint = sub.add_parser("mcp-lint")
    mcp_lint.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default="safe")
    mcp_lint.add_argument("--strict", action="store_true", help="Return non-zero for warnings and errors.")
    mcp_lint.set_defaults(func=cmd_mcp_lint)

    inspector = sub.add_parser("inspector-smoke")
    inspector.add_argument("--endpoint", default="http://127.0.0.1:7331/mcp")
    inspector.add_argument("--run", action="store_true", help="Run MCP Inspector tools/list smoke via npx.")
    inspector.add_argument("--timeout", type=float, default=20.0)
    inspector.add_argument("--strict", action="store_true", help="Return non-zero unless status is pass.")
    inspector.set_defaults(func=cmd_inspector_smoke)

    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("query")
    benchmark.add_argument("path", nargs="?", default=None)
    benchmark.add_argument("--workspace-id")
    benchmark.add_argument("--token-budget", type=int, default=4000)
    benchmark.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default="safe")
    benchmark.add_argument("--no-docs", action="store_true")
    benchmark.add_argument("--reindex", action="store_true")
    benchmark.set_defaults(func=cmd_benchmark)

    retrieval_benchmark = sub.add_parser("retrieval-benchmark")
    retrieval_benchmark.add_argument("path", nargs="?", default=None)
    retrieval_benchmark.add_argument("--workspace-id")
    retrieval_benchmark.add_argument("--cases-file")
    retrieval_benchmark.add_argument("--top-k", type=int, default=3)
    retrieval_benchmark.set_defaults(func=cmd_retrieval_benchmark)

    docs_scan = sub.add_parser("docs-scan")
    docs_scan.add_argument("--workspace-id")
    docs_scan.add_argument("--limit", type=int, default=2000)
    docs_scan.add_argument("--strict", action="store_true", help="Return non-zero when high-risk docs are detected.")
    docs_scan.set_defaults(func=cmd_docs_scan)

    egress = sub.add_parser("egress-report")
    egress.add_argument("--since", help="ISO-8601 lower bound timestamp.")
    egress.add_argument("--limit", type=int, default=100)
    egress.add_argument("--provider", default="context7")
    egress.set_defaults(func=cmd_egress_report)

    pack = sub.add_parser("pack-summary")
    pack.add_argument("query")
    pack.add_argument("--workspace-id")
    pack.add_argument("--token-budget", type=int, default=4000)
    pack.add_argument("--max-files", type=int, default=40)
    pack.add_argument("--no-docs", action="store_true")
    pack.set_defaults(func=cmd_pack_summary)

    blast = sub.add_parser("blast-radius")
    blast.add_argument("query")
    blast.add_argument("--workspace-id")
    blast.add_argument("--depth", type=int, default=1)
    blast.add_argument("--limit", type=int, default=30)
    blast.set_defaults(func=cmd_blast_radius)

    semantic_refs = sub.add_parser("semantic-refs")
    semantic_refs.add_argument("symbol_name")
    semantic_refs.add_argument("--workspace-id")
    semantic_refs.add_argument("--depth", type=int, default=1)
    semantic_refs.add_argument("--limit", type=int, default=30)
    semantic_refs.set_defaults(func=cmd_semantic_refs)

    semantic_impact = sub.add_parser("semantic-impact")
    semantic_impact.add_argument("query")
    semantic_impact.add_argument("--workspace-id")
    semantic_impact.add_argument("--depth", type=int, default=1)
    semantic_impact.add_argument("--limit", type=int, default=30)
    semantic_impact.add_argument("--include-tests", action="store_true")
    semantic_impact.set_defaults(func=cmd_semantic_impact)

    client_check = sub.add_parser("client-check")
    client_check.add_argument("path", nargs="?", default=".")
    client_check.add_argument("--adapter", choices=["codex", "claude", "gemini", "generic"])
    client_check.add_argument("--run", action="store_true", help="Run available local client status commands where safe.")
    client_check.add_argument("--timeout", type=float, default=8.0)
    client_check.add_argument("--strict", action="store_true", help="Return non-zero when attention is needed.")
    client_check.set_defaults(func=cmd_client_check)

    ledger = sub.add_parser("ledger")
    ledger_sub = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_tail = ledger_sub.add_parser("tail")
    ledger_tail.add_argument("--limit", type=int, default=20)
    ledger_tail.add_argument("--query", default="")
    ledger_tail.set_defaults(func=cmd_ledger)
    ledger_show = ledger_sub.add_parser("show")
    ledger_show.add_argument("id")
    ledger_show.set_defaults(func=cmd_ledger)
    ledger_export = ledger_sub.add_parser("export")
    ledger_export.set_defaults(func=cmd_ledger)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except Exception as exc:
        print_json({"status": "error", "error": str(exc), "type": type(exc).__name__})
        return 1


if __name__ == "__main__":
    sys.exit(main())
