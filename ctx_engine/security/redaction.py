from __future__ import annotations

import re

from .secrets import LONG_TOKEN_RE, OPENAI_KEY_RE, SECRET_RE, shannon_entropy


def redact_text(text: str) -> tuple[str, int]:
    redactions = 0

    def redact_named(match: re.Match[str]) -> str:
        nonlocal redactions
        redactions += 1
        return f"{match.group(1)}=<redacted>"

    text = SECRET_RE.sub(redact_named, text)

    def redact_openai(match: re.Match[str]) -> str:
        nonlocal redactions
        redactions += 1
        return "<redacted-openai-key>"

    text = OPENAI_KEY_RE.sub(redact_openai, text)

    def redact_entropy(match: re.Match[str]) -> str:
        nonlocal redactions
        token = match.group(0)
        if len(token) >= 40 and shannon_entropy(token) >= 4.2:
            redactions += 1
            return "<redacted-high-entropy>"
        return token

    text = LONG_TOKEN_RE.sub(redact_entropy, text)
    return text, redactions
