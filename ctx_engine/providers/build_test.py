from __future__ import annotations

import json
from pathlib import Path


class BuildTestProvider:
    def detect(self, root: str | Path, selected_files: list[str] | None = None) -> dict[str, object]:
        root_path = Path(root)
        commands: list[dict[str, str]] = []
        evidence: list[str] = []

        package_json = root_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                for name, command in (data.get("scripts") or {}).items():
                    commands.append({"name": f"npm:{name}", "command": f"npm run {name}", "source": "package.json"})
                evidence.append("package.json")
            except json.JSONDecodeError:
                evidence.append("package.json:unreadable")

        if (root_path / "pyproject.toml").exists() or (root_path / "pytest.ini").exists():
            commands.append({"name": "pytest", "command": "pytest", "source": "python"})
            evidence.append("pytest")
        if (root_path / "tox.ini").exists():
            commands.append({"name": "tox", "command": "tox", "source": "tox.ini"})
            evidence.append("tox.ini")
        if (root_path / "uv.lock").exists():
            commands.append({"name": "uv-pytest", "command": "uv run pytest", "source": "uv.lock"})
            evidence.append("uv.lock")
        if (root_path / "Makefile").exists():
            commands.append({"name": "make-test", "command": "make test", "source": "Makefile"})
            evidence.append("Makefile")
        if (root_path / "justfile").exists() or (root_path / "Justfile").exists():
            commands.append({"name": "just-test", "command": "just test", "source": "justfile"})
            evidence.append("justfile")
        if (root_path / "Dockerfile").exists():
            evidence.append("Dockerfile")
        if (root_path / "docker-compose.yml").exists() or (root_path / "compose.yaml").exists():
            if (root_path / "scripts" / "docker_smoke.ps1").exists():
                commands.append({"name": "docker-smoke", "command": ".\\scripts\\docker_smoke.ps1", "source": "docker-compose"})
            else:
                commands.append({"name": "docker-compose-config", "command": "docker compose config", "source": "docker-compose"})
            evidence.append("docker-compose")
        if (root_path / ".github" / "workflows").exists():
            evidence.append("GitHub Actions")

        suggestions = self._source_to_test_heuristics(root_path, selected_files or [])
        test_plan = self._test_plan(commands, suggestions, selected_files or [])
        return {"commands": commands, "evidence": evidence, "suggested_tests": suggestions, "test_plan": test_plan}

    @staticmethod
    def _source_to_test_heuristics(root: Path, selected_files: list[str]) -> list[str]:
        suggestions: list[str] = []
        for rel in selected_files:
            path = Path(rel)
            stem = path.stem.replace(".test", "").replace(".spec", "")
            base = Path(path.name.replace(".test", "").replace(".spec", "")).stem
            candidates = [
                root / "tests" / f"test_{stem}.py",
                root / "tests" / f"test_{base}.py",
                root / "tests" / f"{stem}.test.ts",
                root / "tests" / f"{stem}.spec.ts",
                root / "tests" / f"{base}.test.ts",
                root / "tests" / f"{base}.spec.ts",
                root / "tests" / f"{stem}.test.js",
                root / "tests" / f"{stem}.spec.js",
                root / "tests" / f"{base}.test.js",
                root / "tests" / f"{base}.spec.js",
                root / "src" / f"{stem}.test.ts",
                root / "src" / f"{base}.test.ts",
                root / "src" / f"{stem}.spec.ts",
                root / "src" / f"{base}.spec.ts",
            ]
            if path.parts and path.parts[0] in {"src", "app"}:
                inner = Path(*path.parts[1:]).with_suffix("")
                candidates.extend(
                    [
                        root / "tests" / f"{inner.as_posix()}.test.ts",
                        root / "tests" / f"{inner.as_posix()}.spec.ts",
                        root / "tests" / f"test_{inner.name}.py",
                    ]
                )
            for candidate in candidates:
                if candidate.exists():
                    suggestions.append(str(candidate.relative_to(root).as_posix()))
            suggestions.extend(BuildTestProvider._import_linked_tests(root, path))
        return sorted(set(suggestions))

    @staticmethod
    def _import_linked_tests(root: Path, rel_path: Path) -> list[str]:
        if not rel_path.suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx"}:
            return []
        tests_dir = root / "tests"
        if not tests_dir.exists():
            return []

        normalized = rel_path.with_suffix("").as_posix()
        dotted = ".".join(rel_path.with_suffix("").parts)
        ts_relative = f"../{normalized}"
        basename = rel_path.stem
        needles = {normalized, dotted, ts_relative, basename}

        patterns = ["test_*.py", "*.test.ts", "*.spec.ts", "*.test.js", "*.spec.js", "*.test.tsx", "*.spec.tsx"]
        matches: list[str] = []
        for pattern in patterns:
            for candidate in tests_dir.rglob(pattern):
                text = candidate.read_text(encoding="utf-8", errors="replace")
                if any(needle and needle in text for needle in needles):
                    matches.append(candidate.relative_to(root).as_posix())
        return matches

    @staticmethod
    def _test_plan(commands: list[dict[str, str]], suggested_tests: list[str], selected_files: list[str]) -> list[dict[str, object]]:
        command_by_name = {item["name"]: item["command"] for item in commands}
        plan: list[dict[str, object]] = []

        for test_path in suggested_tests:
            suffix = Path(test_path).suffix.lower()
            if suffix == ".py" and "pytest" in command_by_name:
                command = f"pytest {test_path}"
                source = "pytest"
            elif suffix in {".js", ".jsx", ".ts", ".tsx"}:
                base = command_by_name.get("npm:test") or command_by_name.get("npm:vitest") or command_by_name.get("npm:test:unit")
                command = f"{base} -- {test_path}" if base else test_path
                source = "package.json" if base else "test-file"
            else:
                command = test_path
                source = "test-file"
            plan.append(
                {
                    "target": test_path,
                    "command": command,
                    "source": source,
                    "reason": "matched selected source file to existing test file",
                    "source_files": selected_files,
                }
            )

        if not plan:
            fallback = command_by_name.get("pytest") or command_by_name.get("npm:test") or command_by_name.get("docker-smoke")
            if fallback:
                plan.append(
                    {
                        "target": "project",
                        "command": fallback,
                        "source": "detected-command",
                        "reason": "no direct test file match; run the nearest project test command",
                        "source_files": selected_files,
                    }
                )
        return plan
