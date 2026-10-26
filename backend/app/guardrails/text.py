"""Input guards: clean a trader's text before it reaches any model, spot injection attempts, and redact personal data.

These run as plain code outside the model, so a clever prompt cannot switch them off. They are cheap (regex only) and
deliberately conservative: a miss is caught by the prompts' scope rules and the output guards, a false alarm only asks
the trader to rephrase. Only counts are logged, never the text itself.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field

log = logging.getLogger("guardrails")

MAX_CHARS = 2000
REFUSAL = (
    "This tool only handles NIFTY and BANKNIFTY options trading: strategies, backtests and paper trading. "
    "Ask me about one of those."
)

# control characters, zero-width characters and bidi overrides (used to hide instructions inside text)
_HIDDEN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁠﻿]")


def sanitize(text: str, max_chars: int = MAX_CHARS) -> str:
    t = unicodedata.normalize("NFKC", text)
    t = _HIDDEN.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()[:max_chars]


_INJECTION = {
    "ignore_instructions": r"\b(ignore|disregard|forget|override)\b[^.\n]{0,30}\b(instructions?|rules|prompts?|guidelines|guardrails)\b",
    "reveal_prompt": r"\b(reveal|print|show|repeat|output|leak|display|tell me)\b[^.\n]{0,25}\b(system|hidden|initial|original|developer)\b[^.\n]{0,12}\b(prompt|instructions?|message)\b",
    "role_override": r"\byou are now\b|\bpretend (to be|you are|you're)\b|\bact as (an? )?(unrestricted|jailbroken|dan|developer|evil)",
    "jailbreak": r"\bjailbreak|\bdo anything now\b|\bdeveloper mode\b|\bDAN\b[^.\n]{0,40}\bno (rules|restrictions|limits)\b",
    "tag_injection": r"</?\s*(system|assistant|scope|instructions|numbers_and_honesty)\s*>",
    "new_instructions": r"\bnew (system )?instructions?\s*:|\bBEGIN (SYSTEM|PROMPT)\b",
}
_INJECTION_RE = {k: re.compile(v, re.I) for k, v in _INJECTION.items()}


def looks_like_injection(text: str) -> str | None:
    """Name of the first injection pattern found in the text, or None."""
    flat = sanitize(text, max_chars=20_000)
    return next((name for name, rx in _INJECTION_RE.items() if rx.search(flat)), None)


def _luhn(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if flip:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total, flip = total + d, not flip
    return total % 10 == 0


_PATTERNS = {
    "email": (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[email]"),
    "secret": (
        re.compile(
            r"\b(?:sk-[A-Za-z0-9_-]{16,}|sk-lf-[0-9a-f-]{16,}|pk-lf-[0-9a-f-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,})\b"
        ),
        "[secret]",
    ),
    "pan": (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[pan]"),
    "aadhaar": (re.compile(r"(?<!\d)(?<!\d,)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)(?!,\d)"), "[aadhaar]"),
    "phone": (re.compile(r"(?<!\d)(?<!\d,)(?:\+?91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)(?!,\d)"), "[phone]"),
}
_CARD = re.compile(r"(?<!\d)(?<!\d,)(?:\d[ -]?){13,16}(?!\d)(?!,\d)")


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Replace emails, API keys, PAN, Aadhaar, phone and card numbers with placeholders. Returns (text, counts)."""
    counts: dict[str, int] = {}

    def swap(name: str, rx: re.Pattern[str], token: str, s: str) -> str:
        s, n = rx.subn(token, s)
        if n:
            counts[name] = counts.get(name, 0) + n
        return s

    for name in ("email", "secret", "pan"):
        text = swap(name, *_PATTERNS[name], text)

    def card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 16 and _luhn(digits):
            counts["card"] = counts.get("card", 0) + 1
            return "[card]"
        return m.group(0)

    text = _CARD.sub(card, text)
    for name in ("aadhaar", "phone"):
        text = swap(name, *_PATTERNS[name], text)
    return text, counts


@dataclass
class Guarded:
    text: str
    injection: str | None = None
    redactions: dict[str, int] = field(default_factory=dict)


def guard_text(text: str, *, source: str, user_id: str | None = None) -> Guarded:
    """Sanitise, check for injection and redact personal data. Logs counts only."""
    clean = sanitize(text)
    injection = looks_like_injection(clean)
    redacted, counts = redact(clean)
    if injection:
        log.warning(
            "guardrail blocked injection",
            extra={"event": "injection", "pattern": injection, "source": source, "user": user_id},
        )
    if counts:
        log.info(
            "guardrail redacted personal data",
            extra={"event": "redaction", "counts": counts, "source": source, "user": user_id},
        )
    return Guarded(redacted, injection, counts)
