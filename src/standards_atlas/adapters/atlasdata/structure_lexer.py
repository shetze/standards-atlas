"""Lexical splitting for Atlas structure tokens."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LexedStructureToken:
    source: str
    body: str
    volume: str | None = None
    enum_prefix: str | None = None


def lex_structure_token(token: str) -> LexedStructureToken:
    """Split volume and enum prefix from a structure token."""
    if not token or token.isspace():
        raise ValueError("Structure token must not be empty.")

    source = token
    volume: str | None = None
    enum_prefix: str | None = None

    if "-" in token:
        prefix, token = token.split("-", 1)
        if not prefix:
            raise ValueError(f"Invalid volume prefix in structure token: {source!r}")
        volume = prefix

    if ":" in token:
        prefix, token = token.split(":", 1)
        if not prefix or not token:
            raise ValueError(f"Invalid enum prefix in structure token: {source!r}")
        enum_prefix = prefix

    return LexedStructureToken(
        source=source,
        body=token,
        volume=volume,
        enum_prefix=enum_prefix,
    )
