"""Private, immutable, hash-addressed evidence; never stored beside public AtlasData."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel

from .knowledge_contract import EvidenceBlob


def canonical_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_write(path: Path, data: bytes, *, private: bool = False) -> bool:
    if path.is_symlink():
        raise ValueError(f"refusing to replace a symlink: {path}")
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600 if private else 0o644)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


class KnowledgeEvidenceStore:
    """Stage writes in memory; validate all destinations before explicit commit."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.pending: dict[str, bytes] = {}

    def put(self, *, kind: str, path: str, value: object) -> str:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        blob = EvidenceBlob(kind=kind, path=path, value=value)
        data = canonical_bytes(blob)
        sha256 = digest(data)
        self.pending[sha256] = data
        return sha256

    def get(self, sha256: str, *, kind: str, path: str) -> object | None:
        if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
            raise ValueError("invalid evidence digest")
        file = self.root / f"{sha256}.json"
        if file.is_symlink():
            raise ValueError("evidence files must not be symlinks")
        data = self.pending.get(sha256)
        if data is None:
            if not file.exists():
                return None
            data = file.read_bytes()
        if digest(data) != sha256:
            raise ValueError(f"private evidence hash mismatch: {sha256}")
        blob = EvidenceBlob.model_validate_json(data)
        if blob.kind != kind or blob.path != path:
            raise ValueError("private evidence kind/path mismatch")
        return blob.value

    def validate_pending(self) -> None:
        for sha256, data in self.pending.items():
            path = self.root / f"{sha256}.json"
            if path.is_symlink() or (path.exists() and path.read_bytes() != data):
                raise ValueError(f"existing private evidence is inconsistent: {sha256}")

    def commit(self) -> None:
        self.validate_pending()
        for sha256, data in sorted(self.pending.items()):
            atomic_write(self.root / f"{sha256}.json", data, private=True)
