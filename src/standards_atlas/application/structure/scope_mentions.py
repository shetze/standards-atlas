"""Deterministic extraction of structure-derived scope mentions."""

from __future__ import annotations

import re

from standards_atlas.domain.model import StructuralScopeMention

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_NUMBER = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
_SCOPE = re.compile(r"\bscope\b", re.I)
_THIS = re.compile(r"\bthis\s+(?:sub)?clause\b", re.I)
_FOLLOWING = re.compile(
    rf"\b(?:the\s+)?following\s+(?:(?P<count>{_NUMBER})\s+)?(?:sub)?clauses?\b",
    re.I,
)
_PRECEDING = re.compile(
    rf"\b(?:the\s+)?(?:preceding|previous)\s+(?:(?P<count>{_NUMBER})\s+)?(?:sub)?clauses?\b",
    re.I,
)


def _count(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.casefold()
    return int(normalized) if normalized.isdigit() else _NUMBER_WORDS.get(normalized)


def extract_structural_scope_mentions(
    text: str,
    *,
    heading: str | None = None,
) -> tuple[StructuralScopeMention, ...]:
    """Return high-recall scope signals without semantic applicability interpretation."""
    mentions: list[StructuralScopeMention] = []
    for match in _SCOPE.finditer(text):
        window = text[max(0, match.start() - 80) : min(len(text), match.end() + 140)]
        this_match = _THIS.search(window)
        following_match = _FOLLOWING.search(window)
        preceding_match = _PRECEDING.search(window)
        if this_match:
            direction = "self"
            cardinality = 1
        elif following_match:
            direction = "forward"
            cardinality = _count(following_match.group("count"))
        elif preceding_match:
            direction = "backward"
            cardinality = _count(preceding_match.group("count"))
        else:
            direction = None
            cardinality = None
        mentions.append(
            StructuralScopeMention(
                source="content",
                surface_text=match.group(0),
                direction_hint=direction,
                cardinality=cardinality,
                status="deferred",
            )
        )
    if heading and _SCOPE.search(heading):
        mentions.append(
            StructuralScopeMention(
                source="heading",
                surface_text=heading,
                direction_hint="subtree",
                status="resolved",
            )
        )
    return tuple(mentions)
