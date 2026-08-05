"""Deterministic hashing primitives used by artifact and domain-specific code."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(value: bytes) -> str:
    """Return the lowercase SHA-256 digest of bytes."""
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str, *, encoding: str = "utf-8") -> str:
    """Return the SHA-256 digest of encoded text."""
    return sha256_bytes(value.encode(encoding))


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it wholly into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    """Return compact, deterministic JSON suitable for fingerprints."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_json(value: Any) -> str:
    """Hash the canonical JSON representation of a value."""
    return sha256_text(canonical_json(value))
