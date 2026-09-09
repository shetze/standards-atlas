"""Verified handoff of one completed archive, never an implicit 'latest' selection."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal
from zipfile import ZipFile

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.shared.hashing import sha256_file


class QualificationArchiveReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    archive_path: str
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    matrix_id: str = Field(min_length=1)


def write_archive_receipt(path: Path, *, archive: Path, matrix_id: str) -> None:
    """Write only after archive creation and identity validation have succeeded."""
    archive = archive.resolve()
    if path.resolve() == archive:
        raise ValueError("archive receipt must not overwrite its archive")
    receipt = QualificationArchiveReceipt(
        archive_path=str(archive), archive_sha256=sha256_file(archive), matrix_id=matrix_id
    )
    _validate_archive(receipt, archive)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def resolve_archive_receipt(path: Path) -> Path:
    """Resolve a checksum- and matrix-verified immutable run for canonical adoption."""
    receipt = QualificationArchiveReceipt.model_validate_json(path.read_text(encoding="utf-8"))
    archive = Path(receipt.archive_path)
    if not archive.is_absolute():
        archive = path.parent / archive
    archive = archive.resolve()
    if sha256_file(archive) != receipt.archive_sha256:
        raise ValueError("qualification archive checksum differs from receipt")
    _validate_archive(receipt, archive)
    return archive


def _validate_archive(receipt: QualificationArchiveReceipt, archive: Path) -> None:
    with ZipFile(archive) as source:
        metadata = json.loads(source.read("archive-manifest.json"))
    if metadata.get("matrix_id") != receipt.matrix_id:
        raise ValueError("qualification archive matrix differs from receipt")
