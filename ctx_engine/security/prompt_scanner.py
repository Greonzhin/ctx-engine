from __future__ import annotations

import re
from dataclasses import dataclass


_INSTRUCTION_OVERRIDE_PATTERNS = [
    re.compile(r"\bignore\s+(all\s+)?(previous|prior)\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\boverride\s+(the\s+)?(system|developer)\s+prompt\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
]

_TOOL_STEERING_PATTERNS = [
    re.compile(r"\b(call|invoke|use)\s+(the\s+)?tool\b", re.IGNORECASE),
    re.compile(r"\b(run|execute)\s+(shell|terminal|command)\b", re.IGNORECASE),
    re.compile(r"\btools?/call\b", re.IGNORECASE),
]

_SECRET_EXFIL_PATTERNS = [
    re.compile(r"\b(print|reveal|dump|leak|exfiltrat\w*)\s+(all\s+)?(secrets?|tokens?|keys?)\b", re.IGNORECASE),
    re.compile(r"\b(cat|read)\s+.*\.(env|pem|key)\b", re.IGNORECASE),
    re.compile(r"\b(base64|curl|wget)\b.*\b(https?://)", re.IGNORECASE),
]

_LINK_BAIT_PATTERNS = [
    re.compile(r"\bclick\s+this\s+link\b", re.IGNORECASE),
    re.compile(r"\bredirect\s+to\s+https?://", re.IGNORECASE),
    re.compile(r"\bdownload\s+and\s+run\b", re.IGNORECASE),
]

_BIDI_CONTROL_CHARS = {
    "\u202a",  # LRE
    "\u202b",  # RLE
    "\u202d",  # LRO
    "\u202e",  # RLO
    "\u202c",  # PDF
    "\u2066",  # LRI
    "\u2067",  # RLI
    "\u2068",  # FSI
    "\u2069",  # PDI
}


def _has_hidden_controls(text: str) -> bool:
    for ch in text:
        if ch in _BIDI_CONTROL_CHARS:
            return True
        code = ord(ch)
        if code < 32 and ch not in {"\n", "\r", "\t"}:
            return True
    return False


@dataclass(frozen=True)
class PromptScanResult:
    risk_level: str
    risk_flags: list[str]
    quarantined: bool


class PromptScanner:
    def scan(self, text: str) -> PromptScanResult:
        flags: list[str] = []

        if any(pattern.search(text) for pattern in _INSTRUCTION_OVERRIDE_PATTERNS):
            flags.append("instruction_override")
        if any(pattern.search(text) for pattern in _TOOL_STEERING_PATTERNS):
            flags.append("tool_steering")
        if any(pattern.search(text) for pattern in _SECRET_EXFIL_PATTERNS):
            flags.append("secret_exfiltration")
        if any(pattern.search(text) for pattern in _LINK_BAIT_PATTERNS):
            flags.append("link_bait_or_redirect")
        if _has_hidden_controls(text):
            flags.append("hidden_unicode_or_control_chars")

        has_exfil = "secret_exfiltration" in flags
        has_hidden = "hidden_unicode_or_control_chars" in flags
        if has_exfil and has_hidden:
            risk = "high"
        elif has_exfil or "instruction_override" in flags or "tool_steering" in flags:
            risk = "medium"
        elif has_hidden or "link_bait_or_redirect" in flags:
            risk = "low"
        else:
            risk = "clean"

        return PromptScanResult(
            risk_level=risk,
            risk_flags=flags,
            quarantined=risk == "high",
        )
