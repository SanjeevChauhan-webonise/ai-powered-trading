"""Output guards: check what an agent wrote before the trader sees it. Used as output validators, so a violation makes the
agent rewrite its answer (a few retries) instead of showing it.

Two rules: no promises of profit and no direct buy/sell orders (an educational tool is not a registered adviser), and the
strategy agent's text must not quote lots, rupee amounts or stop/target percentages (code sets them; quoted ones go stale).
"""

import re

_PROMISES = re.compile(
    r"\bguarantee[ds]?\b|\bsure[- ]?shot\b|\brisk[- ]?free\b|\bassured (returns?|profits?)\b|\b100 ?% (accurate|win|profit|safe|sure)\b|"
    r"\bcan'?t lose\b|\bno risk\b|\bwill (definitely|surely|certainly) (go|rise|fall|profit|win|make)\b|\bcertain (profit|win)\b",
    re.I,
)
_ORDERS = re.compile(
    r"\byou should (buy|sell|enter|invest|exit|short)\b|\b(buy|sell|enter|short) (it |this |that |these )?(immediately|right away|at once)\b|"
    r"\bi (strongly )?recommend (that )?you (buy|sell|enter|invest)\b|\bgo (long|short) now\b",
    re.I,
)
_NEGATION = re.compile(r"\b(cannot|can't|can not|never|not|no|don't|do not|won't|unable|without)\b", re.I)
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")


def advice_violations(text: str) -> list[str]:
    """Phrases that promise profit or give a direct buy/sell order. A sentence that negates it ("I cannot tell you to buy
    now") is fine."""
    found: list[str] = []
    for sentence in _SENTENCES.split(text):
        if _NEGATION.search(sentence):
            continue
        for rx in (_PROMISES, _ORDERS):
            m = rx.search(sentence)
            if m:
                found.append(m.group(0).lower())
    return found


_QUOTED_NUMBERS = re.compile(
    r"₹\s?\d|\bRs\.?\s?\d|\bINR\s?\d|\b\d+\s+lots?\b|"
    r"\b(stop(?:[- ]?loss)?|target|trailing(?: stop)?)\b[^.\n]{0,24}?\d+(?:\.\d+)?\s?%|\d+(?:\.\d+)?\s?%[^.\n]{0,14}\b(stop|target)\b",
    re.I,
)


def quoted_number_violations(text: str) -> list[str]:
    return [m.group(0) for m in _QUOTED_NUMBERS.finditer(text)]
