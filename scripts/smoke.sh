#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export CTX_ENGINE_DATA_DIR="${CTX_ENGINE_DATA_DIR:-$ROOT/.tmp-smoke-data}"

ctx init .
ctx index tests/fixtures/python_app
ctx index tests/fixtures/ts_app
ctx status
ctx capsule "where is auth handled?" >/dev/null
ctx memory add "Authentication middleware lives in app/middleware.py" >/dev/null
ctx memory search "authentication middleware" >/dev/null
ctx docs resolve fastapi >/dev/null
ctx docs query /tiangolo/fastapi "routing dependencies" >/dev/null
ctx install codex
ctx install claude
ctx install gemini
ctx doctor >/dev/null
ctx path check >/dev/null
