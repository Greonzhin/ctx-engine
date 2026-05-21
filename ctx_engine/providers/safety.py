from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..security.ignore import is_ignored, to_posix_rel
from ..security.redaction import redact_text
from ..security.secrets import find_secret_markers, looks_sensitive_path


class SafetyViolation(ValueError):
    """Raised when a provider request violates the P0 safety posture."""


PRIVATE_SOURCE_RE = re.compile(
    r"(?s)(\bclass\s+\w+|\bdef\s+\w+|\bfunction\s+\w+|=>\s*\{|"
    r"\bimport\s+.+\bfrom\b|BEGIN\s+PRIVATE|internal\s+openapi|proprietary)"
)


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str
    redactions: int = 0
    text: str = ""


class SafetyProvider:
    def can_read_file(self, path: Path, root: Path) -> SafetyDecision:
        rel = to_posix_rel(path, root)
        if is_ignored(rel) or looks_sensitive_path(path):
            return SafetyDecision(False, f"ignored sensitive path: {rel}")
        return SafetyDecision(True, "allowed")

    def redact(self, text: str) -> SafetyDecision:
        redacted, count = redact_text(text)
        return SafetyDecision(True, "redacted" if count else "clean", count, redacted)

    def guard_external_docs_query(self, query: str) -> SafetyDecision:
        markers = find_secret_markers(query)
        redacted, count = redact_text(query)
        if markers:
            raise SafetyViolation("external docs query contains secret-like content")
        if len(redacted) > 800:
            redacted = redacted[:800]
            count += 1
        if "\n" in query and PRIVATE_SOURCE_RE.search(query):
            raise SafetyViolation("external docs query appears to contain private source")
        if PRIVATE_SOURCE_RE.search(query) and len(query) > 160:
            raise SafetyViolation("external docs query appears to contain private source")
        return SafetyDecision(True, "external-docs-query-allowed", count, redacted)
