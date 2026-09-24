"""Input guard — cheap, deterministic prompt-injection / jailbreak detector.

A meeting transcript is UNTRUSTED (see the trust model + Prompt_injection.md):
its text is DATA, never instructions. `contains_injection(text)` is a first-line
filter that returns the matched snippet when `text` looks like it is trying to
override instructions, reassign the model's role, or exfiltrate the system prompt,
and None when it looks clean.

It is deliberately CONSERVATIVE — a small set of well-known override phrasings,
not broad matching — so ordinary meeting content is not rejected. It is a
first-line filter, NOT a complete defense.
"""

from __future__ import annotations

import re

# Each pattern targets a well-known instruction-override, role-reassignment, or
# secret-exfiltration phrasing. Case-insensitive; matched against normalised text.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|preceding|earlier)\s+(?:instruction|prompt|message|context|rule)s?", re.I),
    re.compile(r"disregard\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|preceding|earlier|system)\s+(?:instruction|prompt|message|rule|guardrail)s?", re.I),
    re.compile(r"forget\s+(?:everything|all|your|the)\s+(?:above|previous|prior|instruction)", re.I),
    re.compile(r"override\s+(?:your\s+|the\s+)?(?:previous\s+|system\s+)?(?:instruction|prompt|guardrail|safety|rule)s?", re.I),
    re.compile(r"\bsystem\s+prompt\b", re.I),
    re.compile(r"\byou\s+are\s+now\s+(?:a\s+|an\s+)?(?:different|new|unrestricted|dan\b|developer|admin|root)", re.I),
    re.compile(r"\bpretend\s+(?:to\s+be|you\s+are)\b", re.I),
    re.compile(r"\bact\s+as\s+(?:a\s+|an\s+|the\s+)?(?:different|unrestricted|jailbroken|admin|root|system)\b", re.I),
    re.compile(r"\bdeveloper\s+mode\b", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bdo\s+anything\s+now\b", re.I),
    re.compile(r"reveal\s+(?:your\s+|the\s+)?(?:system\s+)?(?:prompt|instruction|secret|api\s+key)s?", re.I),
    re.compile(r"(?:print|show|repeat|output)\s+(?:your\s+|the\s+)?(?:system\s+)?(?:prompt|instruction)s?", re.I),
    re.compile(r"(?:store|save|remember)\s+this\s+as\s+(?:a\s+)?(?:permanent|system|core|standing)\s+(?:instruction|rule|directive)", re.I),
)

# Collapse whitespace runs so a pattern still matches across newlines / odd spacing.
_WHITESPACE = re.compile(r"\s+")


def contains_injection(text: str) -> str | None:
    """Return the matched snippet if `text` looks like a prompt-injection attempt, else None."""
    if not text or not isinstance(text, str):
        return None
    normalised = _WHITESPACE.sub(" ", text)
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(normalised)
        if match:
            return match.group(0)
    return None
