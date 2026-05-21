from __future__ import annotations

import math
import re
from pathlib import Path

SENSITIVE_NAME_RE = re.compile(
    r"(^\.env(\..*)?$|\.pem$|\.key$|\.p12$|\.sqlite$|\.db$|\.dump$)",
    re.IGNORECASE,
)
SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization|credential)\b"
    r"\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})"
)
OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}\b")
LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9+/=_-]{32,}\b")


def looks_sensitive_path(path: str | Path) -> bool:
    name = Path(path).name
    return bool(SENSITIVE_NAME_RE.search(name))


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {ch: value.count(ch) for ch in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def has_high_entropy_secret(text: str) -> bool:
    for match in LONG_TOKEN_RE.finditer(text):
        token = match.group(0)
        if len(token) >= 40 and shannon_entropy(token) >= 4.2:
            return True
    return False


def find_secret_markers(text: str) -> list[str]:
    markers: list[str] = []
    if SECRET_RE.search(text):
        markers.append("named-secret")
    if OPENAI_KEY_RE.search(text):
        markers.append("openai-key")
    if has_high_entropy_secret(text):
        markers.append("high-entropy")
    return markers
