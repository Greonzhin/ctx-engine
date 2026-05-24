# Jules Bolt Runbook

Jules runs tasks in a short-lived Ubuntu VM, clones the repo, installs dependencies, and can use the root `AGENTS.md` file for project instructions. Use this runbook when starting a Jules task with the Bolt performance prompt.

## Jules Setup

Use `.jules/setup.sh` as the Initial Setup reference in Jules:

```bash
bash .jules/setup.sh
```

The setup is intentionally finite and lightweight. Do not use long-running dev servers or watch commands in Jules setup.

## Correct Bolt Behavior

Before changing code, Bolt should:

- Read `.jules/bolt.md`; create it only if missing.
- Inspect the repo and run targeted profiling or benchmark commands before choosing an optimization.
- Pick one measurable optimization that is small, low risk, and readable.
- Stop without a PR if no clear performance win is found.

This is a Python project, so Bolt should use:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ctx_engine.cli benchmark "where is auth handled?"
python -m ctx_engine.cli retrieval-benchmark . --top-k 3
```

Do not use `pnpm lint` or `pnpm test` for the main repo unless the task explicitly targets the JavaScript fixture.

## Review Of The Current Jules Reply

The current reply correctly avoided making an unmeasured optimization, but it should be tightened:

- It should read `.jules/bolt.md` first.
- It should not ask for known bottlenecks until it has completed repo-local profiling.
- It should prefer measurable repo commands such as `ctx benchmark`, `retrieval-benchmark`, and targeted pytest over micro-optimizing string containment loops.
- It must avoid `package.json` and `tsconfig.json` changes unless explicitly instructed.

Recommended response to Jules:

```text
Proceed without asking for a user-selected bottleneck. First read .jules/bolt.md, run the Python setup/tests from .jules/setup.sh, then profile one concrete hot path with existing benchmark or retrieval-benchmark commands. Pick only one optimization under 50 changed lines. Do not change pyproject.toml, Docker runtime files, generated client files, or MCP tool names. If no measurable win appears, stop and report that no PR should be created.
```
