from __future__ import annotations

import fnmatch
from pathlib import Path

from ..config import IGNORED_PATHS


def to_posix_rel(path: Path, root: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        rel = path
    return rel.as_posix()


def is_ignored(rel_path: str, patterns: list[str] | None = None) -> bool:
    rel = rel_path.replace("\\", "/").lstrip("./")
    parts = rel.split("/")
    patterns = patterns or IGNORED_PATHS
    for pattern in patterns:
        pat = pattern.replace("\\", "/")
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(Path(rel).name, pat):
            return True
        if pat.endswith("/**") and parts and parts[0] == pat[:-3]:
            return True
    return False


def filter_walk_dirs(root: Path, dirs: list[str]) -> None:
    kept = []
    for name in dirs:
        rel = (Path(name)).as_posix()
        if not is_ignored(rel) and not is_ignored(f"{rel}/"):
            kept.append(name)
    dirs[:] = kept
