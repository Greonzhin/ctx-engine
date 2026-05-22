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
from .hooks import SUPPORTED_HOOK_CLIENTS, hook_plan
from .inspector_smoke import inspector_smoke
from .log_compression import compress_log_file, compress_log_text
from .mcp_contract import check_gateway_contract, check_http_gateway_contract
from .mcp_lint import lint_gateway_tools
from .pathmap import check_paths, map_path
from .policy import evaluate_policy
from .providers.action_ledger import ActionLedger
from .providers.capsule_feedback import CapsuleFeedbackProvider, VALID_FEEDBACK_RATINGS
from .providers.code_graph import CodeGraphProvider
from .providers.egress import EgressProvider
from .providers.context7_docs import Context7DocsProvider
from .providers.local_docs import LocalDocsProvider
from .providers.memory import BuiltInMemoryProvider
from .pack_summary import pack_summary
from .retrieval_benchmark import run_retrieval_benchmark
from .rules_check import check_rules_drift
from .security_scan import SUPPORTED_SCANNERS, scan_security
from .server import serve
from .skill_pack import build_skill_pack, list_skill_packs, render_skill_pack, write_skill_pack
from .verified_cache import verify_capsule_cache
from .workflow import list_workflows, show_workflow, suggest_workflow
from .workspace import clear_active_workspace, get_workspace, list_workspaces, register_workspace, set_active_workspace, workspace_inventory


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


def cmd_workspace(args: argparse.Namespace) -> int:
    if args.workspace_command == "list":
        print_json(workspace_inventory())
        return 0
    if args.workspace_command == "add":
        result = register_workspace(args.path, display_name=args.name)
        activated = False
        if args.activate:
            result = set_active_workspace(result["id"])
            activated = True
        print_json({"status": "ok", "workspace": result, "activated": activated})
        return 0
    if args.workspace_command == "use":
        workspace = set_active_workspace(args.workspace)
        print_json({"status": "ok", "active_workspace": workspace})
        return 0
    if args.workspace_command == "show":
        print_json({"status": "ok", "active_workspace": get_workspace()})
        return 0
    if args.workspace_command == "clear":
        clear_active_workspace()
        print_json({"status": "ok", "active_workspace": get_workspace()})
        return 0
    if args.workspace_command == "check":
        result = workspace_inventory()
        print_json(result)
        if args.strict:
            return 0 if result["status"] == "ok" and result["workspace_count"] > 0 else 1
        return 0
    raise SystemExit("unknown workspace command")


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
        print("\n## Test Plan")
        for item in capsule.get("build_test_context", {}).get("test_plan", []):
            print(f"- {item['command']} ({item['reason']})")
        workflow = capsule.get("workflow_context", {}).get("recipe", {})
        if workflow:
            print("\n## Workflow")
            print(f"- {workflow['name']}: {workflow['intent']}")
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


def cmd_security_scan(args: argparse.Namespace) -> int:
    result = scan_security(
        args.path,
        scanner=args.scanner,
        all_scanners=args.all,
        strict=args.strict,
        timeout=args.timeout,
    )
    print_json(result)
    return 1 if args.strict and result["status"] in {"fail", "findings"} else 0


def cmd_workflow(args: argparse.Namespace) -> int:
    if args.workflow_command == "list":
        print_json(list_workflows())
    elif args.workflow_command == "show":
        result = show_workflow(args.name)
        print_json(result)
        return 0 if result["status"] == "ok" else 1
    elif args.workflow_command == "suggest":
        print_json(suggest_workflow(args.query))
    else:
        raise SystemExit("unknown workflow command")
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    if args.rules_command != "check":
        raise SystemExit("unknown rules command")
    result = check_rules_drift(args.path)
    print_json(result)
    if args.strict:
        return 0 if result["status"] == "ok" else 1
    return 0


def cmd_hooks(args: argparse.Namespace) -> int:
    if args.hooks_command != "plan":
        raise SystemExit("unknown hooks command")
    print_json(hook_plan(args.client))
    return 0


def cmd_compress_log(args: argparse.Namespace) -> int:
    if args.file:
        result = compress_log_file(args.file, max_lines=args.max_lines)
    else:
        result = compress_log_text(sys.stdin.read(), max_lines=args.max_lines)
        result["source"] = "stdin"
    print_json(result)
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    provider = CapsuleFeedbackProvider()
    if args.feedback_command == "record":
        result = provider.record(
            args.capsule_id,
            args.rating,
            workspace_id=args.workspace_id,
            client_id=args.client_id,
            useful_files=args.useful_file,
            missing_files=args.missing_file,
            notes=args.notes or "",
        )
        print_json(result)
    elif args.feedback_command == "report":
        print_json(provider.report(capsule_id=args.capsule_id, workspace_id=args.workspace_id, limit=args.limit))
    else:
        raise SystemExit("unknown feedback command")
    return 0


def cmd_skill_pack(args: argparse.Namespace) -> int:
    if args.skill_pack_command == "list":
        print_json(list_skill_packs())
        return 0
    if args.skill_pack_command == "generate":
        pack = build_skill_pack(args.name_or_query)
        if args.output:
            print_json(write_skill_pack(pack, args.output))
        else:
            print(render_skill_pack(pack, args.format))
        return 0
    raise SystemExit("unknown skill-pack command")


def cmd_cache(args: argparse.Namespace) -> int:
    if args.cache_command != "verify":
        raise SystemExit("unknown cache command")
    result = verify_capsule_cache(workspace_id=args.workspace_id, limit=args.limit)
    print_json(result)
    if args.strict:
        return 0 if result["status"] == "ok" else 1
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    if args.policy_command != "check":
        raise SystemExit("unknown policy command")
    result = evaluate_policy(args.path, mode=args.mode)
    print_json(result)
    if args.strict:
        return 0 if result["status"] == "pass" else 1
    return 0


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

    workspace = sub.add_parser("workspace")
    workspace_sub = workspace.add_subparsers(dest="workspace_command", required=True)
    workspace_list = workspace_sub.add_parser("list")
    workspace_list.set_defaults(func=cmd_workspace)
    workspace_add = workspace_sub.add_parser("add")
    workspace_add.add_argument("path")
    workspace_add.add_argument("--name")
    workspace_add.add_argument("--activate", action="store_true")
    workspace_add.set_defaults(func=cmd_workspace)
    workspace_use = workspace_sub.add_parser("use")
    workspace_use.add_argument("workspace", help="Workspace id or path inside a registered workspace.")
    workspace_use.set_defaults(func=cmd_workspace)
    workspace_show = workspace_sub.add_parser("show")
    workspace_show.set_defaults(func=cmd_workspace)
    workspace_clear = workspace_sub.add_parser("clear")
    workspace_clear.set_defaults(func=cmd_workspace)
    workspace_check = workspace_sub.add_parser("check")
    workspace_check.add_argument("--strict", action="store_true", help="Return non-zero when no workspace exists or a registered path is missing.")
    workspace_check.set_defaults(func=cmd_workspace)

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

    security_scan = sub.add_parser("security-scan")
    security_scan.add_argument("path", nargs="?", default=".")
    security_scan.add_argument("--scanner", choices=SUPPORTED_SCANNERS, default="semgrep")
    security_scan.add_argument("--all", action="store_true", help="Run all supported optional scanners.")
    security_scan.add_argument("--timeout", type=float, default=60.0)
    security_scan.add_argument("--strict", action="store_true", help="Return non-zero for missing scanners, scanner errors, or findings.")
    security_scan.set_defaults(func=cmd_security_scan)

    workflow = sub.add_parser("workflow")
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_list = workflow_sub.add_parser("list")
    workflow_list.set_defaults(func=cmd_workflow)
    workflow_show = workflow_sub.add_parser("show")
    workflow_show.add_argument("name")
    workflow_show.set_defaults(func=cmd_workflow)
    workflow_suggest = workflow_sub.add_parser("suggest")
    workflow_suggest.add_argument("query")
    workflow_suggest.set_defaults(func=cmd_workflow)

    rules = sub.add_parser("rules")
    rules_sub = rules.add_subparsers(dest="rules_command", required=True)
    rules_check = rules_sub.add_parser("check")
    rules_check.add_argument("path", nargs="?", default=".")
    rules_check.add_argument("--strict", action="store_true", help="Return non-zero when generated files drift from .ctx-engine/rules.yaml.")
    rules_check.set_defaults(func=cmd_rules)

    hooks = sub.add_parser("hooks")
    hooks_sub = hooks.add_subparsers(dest="hooks_command", required=True)
    hooks_plan = hooks_sub.add_parser("plan")
    hooks_plan.add_argument("client", nargs="?", default="all", choices=["all", *SUPPORTED_HOOK_CLIENTS])
    hooks_plan.set_defaults(func=cmd_hooks)

    compress_log = sub.add_parser("compress-log")
    compress_log.add_argument("file", nargs="?")
    compress_log.add_argument("--max-lines", type=int, default=80)
    compress_log.set_defaults(func=cmd_compress_log)

    feedback = sub.add_parser("feedback")
    feedback_sub = feedback.add_subparsers(dest="feedback_command", required=True)
    feedback_record = feedback_sub.add_parser("record")
    feedback_record.add_argument("capsule_id")
    feedback_record.add_argument("--rating", required=True, choices=VALID_FEEDBACK_RATINGS)
    feedback_record.add_argument("--workspace-id")
    feedback_record.add_argument("--client-id", default="cli")
    feedback_record.add_argument("--useful-file", action="append", default=[])
    feedback_record.add_argument("--missing-file", action="append", default=[])
    feedback_record.add_argument("--notes", default="")
    feedback_record.set_defaults(func=cmd_feedback)
    feedback_report = feedback_sub.add_parser("report")
    feedback_report.add_argument("capsule_id", nargs="?")
    feedback_report.add_argument("--workspace-id")
    feedback_report.add_argument("--limit", type=int, default=50)
    feedback_report.set_defaults(func=cmd_feedback)

    skill_pack = sub.add_parser("skill-pack")
    skill_pack_sub = skill_pack.add_subparsers(dest="skill_pack_command", required=True)
    skill_pack_list = skill_pack_sub.add_parser("list")
    skill_pack_list.set_defaults(func=cmd_skill_pack)
    skill_pack_generate = skill_pack_sub.add_parser("generate")
    skill_pack_generate.add_argument("name_or_query")
    skill_pack_generate.add_argument("--format", choices=["json", "markdown"], default="json")
    skill_pack_generate.add_argument("--output", help="Write SKILL.md and skill-pack.json to this directory.")
    skill_pack_generate.set_defaults(func=cmd_skill_pack)

    cache = sub.add_parser("cache")
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)
    cache_verify = cache_sub.add_parser("verify")
    cache_verify.add_argument("workspace_id", nargs="?")
    cache_verify.add_argument("--limit", type=int, default=100)
    cache_verify.add_argument("--strict", action="store_true", help="Return non-zero when stale or invalid capsule cache entries are found.")
    cache_verify.set_defaults(func=cmd_cache)

    policy = sub.add_parser("policy")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    policy_check = policy_sub.add_parser("check")
    policy_check.add_argument("path", nargs="?", default=".")
    policy_check.add_argument("--mode", choices=sorted(SUPPORTED_MODES), default="safe")
    policy_check.add_argument("--strict", action="store_true", help="Return non-zero when policy checks fail.")
    policy_check.set_defaults(func=cmd_policy)

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
