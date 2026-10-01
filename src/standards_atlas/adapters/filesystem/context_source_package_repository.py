"""Private hash-addressed persistence for AP02 context source packages."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from standards_atlas.application.context.input_binding import (
    CONTEXT_SOURCE_PACKAGE_SCHEMA_VERSION,
    ContextSourcePackage,
    ContextSourcePackageBinding,
    context_source_package_binding,
)
from standards_atlas.application.schema import require_current_payload, require_supported_schema

CURRENT_CONTEXT_SOURCE_PACKAGE_SCHEMA_VERSION = CONTEXT_SOURCE_PACKAGE_SCHEMA_VERSION


class FileSystemContextSourcePackageRepository:
    """Persist protected source packages immutably and expose only text-free bindings."""

    def __init__(self, workspace: Path = Path(".atlas/data")) -> None:
        self._root = workspace / "context-source-packages"

    def save(self, package: ContextSourcePackage) -> ContextSourcePackageBinding:
        payload = package.model_dump(mode="json")
        require_current_payload("context-source-package", payload)
        data = _canonical_bytes(payload)
        digest = hashlib.sha256(data).hexdigest()
        path = self._root / f"{digest}.json"
        _atomic_private_write(path, data)
        return context_source_package_binding(package, package_sha256=f"sha256:{digest}")

    def load(self, binding: ContextSourcePackageBinding) -> ContextSourcePackage | None:
        digest = binding.package_sha256.removeprefix("sha256:")
        path = self._root / f"{digest}.json"
        if path.is_symlink():
            raise ValueError("context source package files must not be symlinks")
        if not path.is_file():
            return None
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("context source package content hash mismatch")
        payload = json.loads(data)
        require_supported_schema("context-source-package", payload.get("schema_version"))
        package = ContextSourcePackage.model_validate(payload)
        expected = context_source_package_binding(package, package_sha256=binding.package_sha256)
        if expected != binding:
            raise ValueError("context source package does not match its public binding")
        return package


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _atomic_private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.is_symlink():
        raise ValueError(f"refusing to replace a symlink: {path}")
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("hash-addressed context source package path contains different bytes")
        os.chmod(path, 0o600)
        return
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
