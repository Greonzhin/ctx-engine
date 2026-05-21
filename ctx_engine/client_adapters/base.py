from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import DEFAULT_ENDPOINT, ensure_project_config, load_endpoint_from_rules


@dataclass(frozen=True)
class InstallResult:
    client_id: str
    workspace_path: str
    files: list[str]
    endpoint: str


class ClientAdapter:
    client_id = "generic"

    def detect(self, workspace_path: str | Path) -> bool:
        root = Path(workspace_path).resolve()
        expected = self.expected_files(root)
        if expected:
            return all(path.exists() for path in expected)
        return root.exists()

    def install(self, workspace_path: str | Path) -> InstallResult:
        root = Path(workspace_path).resolve()
        ensure_project_config(root, DEFAULT_ENDPOINT)
        endpoint = load_endpoint_from_rules(root)
        files = self.write_files(root, endpoint)
        return InstallResult(self.client_id, str(root), [str(path) for path in files], endpoint)

    def write_files(self, root: Path, endpoint: str) -> list[Path]:
        raise NotImplementedError

    def expected_files(self, root: Path) -> list[Path]:
        return []

    def read_configured_endpoint(self, root: Path) -> str | None:
        return None

    def status(self, workspace_path: str | Path) -> dict[str, object]:
        root = Path(workspace_path).resolve()
        expected = self.expected_files(root)
        files = {path.relative_to(root).as_posix(): path.exists() for path in expected}
        rules_endpoint = load_endpoint_from_rules(root)
        configured_endpoint = self.read_configured_endpoint(root)
        installed = self.detect(root)
        return {
            "client_id": self.client_id,
            "workspace_path": str(root),
            "installed": installed,
            "files": files,
            "missing_files": [name for name, exists in files.items() if not exists],
            "rules_endpoint": rules_endpoint,
            "configured_endpoint": configured_endpoint,
            "endpoint_matches_rules": None if configured_endpoint is None else configured_endpoint == rules_endpoint,
        }
