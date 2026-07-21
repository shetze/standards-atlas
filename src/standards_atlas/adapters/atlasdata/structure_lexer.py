"""Lexical splitting for Atlas structure tokens."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LexedStructureToken:
    source: str
    body: str
    volume: str | None = None


def lex_structure_token(token: str) -> LexedStructureToken:
    """Split an optional volume prefix from a structure token.

    Type and enumeration prefixes deliberately remain in ``body`` because
    their order is significant. Historical AtlasData uses
    ``[type][enum]:reference`` while a small number of generated files use
    ``enum:[type]reference``. The parser accepts both spellings.
    """
    if not token or token.isspace():
        raise ValueError("Structure token must not be empty.")

    source = token
    volume: str | None = None

    if "-" in token:
        prefix, token = token.split("-", 1)
        if not prefix or not token:
            raise ValueError(f"Invalid volume prefix in structure token: {source!r}")
        volume = prefix

    return LexedStructureToken(
        source=source,
        body=token,
        volume=volume,
    )
