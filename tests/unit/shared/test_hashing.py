from __future__ import annotations

import hashlib
from pathlib import Path

from standards_atlas.shared.hashing import (
    canonical_json,
    sha256_bytes,
    sha256_file,
    sha256_json,
    sha256_text,
)


def test_sha256_helpers_match_hashlib(tmp_path: Path) -> None:
    payload = "Grüße"
    path = tmp_path / "payload.txt"
    path.write_text(payload, encoding="utf-8")
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    assert sha256_bytes(payload.encode("utf-8")) == expected
    assert sha256_text(payload) == expected
    assert sha256_file(path) == expected


def test_canonical_json_hash_is_order_independent() -> None:
    left = {"b": 2, "a": "Ä"}
    right = {"a": "Ä", "b": 2}

    assert canonical_json(left) == '{"a":"Ä","b":2}'
    assert sha256_json(left) == sha256_json(right)
