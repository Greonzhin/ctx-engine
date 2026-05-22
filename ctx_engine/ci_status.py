from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


SUPPORTED_CI_PROVIDERS = ("github-actions",)


def _run_command(command: list[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_workflow(path: Path, root: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    workflow_name = path.stem
    triggers: list[str] = []
    jobs: list[dict[str, str]] = []
    in_on = False
    in_jobs = False
    current_job: dict[str, str] | None = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        name_match = re.match(r"^name:\s*(.+)$", line)
        if name_match and not in_jobs:
            workflow_name = _strip_quotes(name_match.group(1))
            continue

        if re.match(r"^on:\s*$", line):
            in_on = True
            in_jobs = False
            continue
        if re.match(r"^jobs:\s*$", line):
            in_on = False
            in_jobs = True
            continue
        if re.match(r"^\S[^:]*:\s*$", line):
            in_on = False
            if not line.startswith("jobs:"):
                in_jobs = False

        if in_on:
            trigger_match = re.match(r"^\s{2}([A-Za-z0-9_-]+):?\s*$", line)
            if trigger_match:
                triggers.append(trigger_match.group(1))
            continue

        if in_jobs:
            job_match = re.match(r"^\s{2}([A-Za-z0-9_-]+):\s*$", line)
            if job_match:
                current_job = {"id": job_match.group(1), "name": job_match.group(1)}
                jobs.append(current_job)
                continue
            display_name_match = re.match(r"^\s{4}name:\s*(.+)$", line)
            if current_job is not None and display_name_match:
                current_job["name"] = _strip_quotes(display_name_match.group(1))

    return {
        "path": path.relative_to(root).as_posix(),
        "name": workflow_name,
        "triggers": sorted(set(triggers)),
        "jobs": jobs,
        "job_count": len(jobs),
    }


def _workflow_files(root: Path) -> list[Path]:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.exists():
        return []
    files = list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml"))
    return sorted(files)


def _parse_gh_runs(stdout: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not stdout.strip():
        return [], []
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return [], [f"gh run list returned non-JSON output: {exc}"]
    if not isinstance(payload, list):
        return [], ["gh run list returned unexpected JSON shape"]

    runs: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        runs.append(
            {
                "database_id": item.get("databaseId"),
                "workflow_name": item.get("workflowName") or "",
                "display_title": item.get("displayTitle") or "",
                "head_branch": item.get("headBranch") or "",
                "status": item.get("status") or "",
                "conclusion": item.get("conclusion") or "",
                "created_at": item.get("createdAt") or "",
                "url": item.get("url") or "",
            }
        )
    return runs, []


def _parse_run_jobs(stdout: str, run_id: object) -> tuple[dict[str, Any], list[str]]:
    if not stdout.strip():
        return {"run_id": run_id, "jobs": [], "empty_step_jobs": []}, []
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"run_id": run_id, "jobs": [], "empty_step_jobs": []}, [f"gh run view {run_id} returned non-JSON output: {exc}"]
    if not isinstance(payload, dict):
        return {"run_id": run_id, "jobs": [], "empty_step_jobs": []}, [f"gh run view {run_id} returned unexpected JSON shape"]

    jobs: list[dict[str, Any]] = []
    for item in payload.get("jobs", []):
        if not isinstance(item, dict):
            continue
        steps = item.get("steps")
        step_count = len(steps) if isinstance(steps, list) else 0
        jobs.append(
            {
                "database_id": item.get("databaseId"),
                "name": item.get("name") or "",
                "status": item.get("status") or "",
                "conclusion": item.get("conclusion") or "",
                "started_at": item.get("startedAt") or "",
                "completed_at": item.get("completedAt") or "",
                "url": item.get("url") or "",
                "step_count": step_count,
            }
        )

    empty_step_jobs = [item for item in jobs if item.get("status") == "completed" and item.get("conclusion") == "failure" and item.get("step_count") == 0]
    return {"run_id": run_id, "jobs": jobs, "empty_step_jobs": empty_step_jobs}, []


def ci_status(
    path: str | Path = ".",
    provider: str = "github-actions",
    run: bool = False,
    strict: bool = False,
    timeout: float = 10.0,
    limit: int = 5,
) -> dict[str, Any]:
    root = Path(path).resolve()
    warnings: list[str] = []
    errors: list[str] = []

    if provider not in SUPPORTED_CI_PROVIDERS:
        errors.append(f"unsupported CI provider: {provider}")
        return {
            "status": "fail",
            "provider": provider,
            "path": str(root),
            "workflows": [],
            "workflow_count": 0,
            "runtime": {"checked": False, "command_available": False, "runs": []},
            "warnings": warnings,
            "errors": errors,
        }

    workflows = [_parse_workflow(workflow, root) for workflow in _workflow_files(root)]
    if not workflows:
        message = "no GitHub Actions workflow files found"
        warnings.append(message)
        if strict:
            errors.append(message)

    runtime: dict[str, Any] = {"checked": False, "command_available": shutil.which("gh") is not None, "runs": []}
    if run:
        runtime["checked"] = True
        if not runtime["command_available"]:
            message = "gh command is not available"
            warnings.append(message)
            if strict:
                errors.append(message)
        else:
            command = [
                "gh",
                "run",
                "list",
                "--limit",
                str(limit),
                "--json",
                "databaseId,status,conclusion,workflowName,headBranch,displayTitle,createdAt,url",
            ]
            runtime["command"] = command
            try:
                completed = _run_command(command, root, timeout)
            except (OSError, subprocess.TimeoutExpired) as exc:
                message = f"gh run list failed to run: {exc}"
                warnings.append(message)
                errors.append(message)
            else:
                runtime["returncode"] = completed.returncode
                runs, parse_warnings = _parse_gh_runs(completed.stdout)
                runtime["runs"] = runs
                warnings.extend(parse_warnings)
                if completed.returncode != 0:
                    errors.append(f"gh run list returned exit code {completed.returncode}")
                failing_runs = [item for item in runs if item.get("status") == "completed" and item.get("conclusion") == "failure"]
                runtime["failing_runs"] = failing_runs
                diagnostics: list[dict[str, Any]] = []
                empty_step_failures: list[dict[str, Any]] = []
                for run_item in failing_runs[: min(limit, 3)]:
                    run_id = run_item.get("database_id")
                    if not run_id:
                        continue
                    view_command = ["gh", "run", "view", str(run_id), "--json", "jobs"]
                    try:
                        view_completed = _run_command(view_command, root, timeout)
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        message = f"gh run view {run_id} failed to run: {exc}"
                        warnings.append(message)
                        continue
                    if view_completed.returncode != 0:
                        warnings.append(f"gh run view {run_id} returned exit code {view_completed.returncode}")
                        continue
                    diagnostic, parse_warnings = _parse_run_jobs(view_completed.stdout, run_id)
                    diagnostics.append(diagnostic)
                    warnings.extend(parse_warnings)
                    empty_step_failures.extend(diagnostic["empty_step_jobs"])
                runtime["job_diagnostics"] = diagnostics
                runtime["empty_step_failures"] = empty_step_failures
                if empty_step_failures:
                    warnings.append("GitHub Actions has failing jobs with zero recorded steps; this usually points to runner/platform setup before workflow steps start.")
                if strict and failing_runs:
                    errors.append("GitHub Actions has failing completed runs")

    status = "ok"
    if errors:
        status = "fail"
    elif warnings:
        status = "warn"

    return {
        "status": status,
        "provider": provider,
        "path": str(root),
        "workflows": workflows,
        "workflow_count": len(workflows),
        "runtime": runtime,
        "warnings": sorted(warnings),
        "errors": sorted(errors),
    }
