#!/usr/bin/env bash
set -euo pipefail

python -m pip install -e ".[dev]"
python -m pytest -q tests/test_docker_files.py tests/test_client_adapters.py tests/test_ci_status.py
