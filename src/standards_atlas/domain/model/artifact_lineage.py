"""Deterministic lineage metadata for generated artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ArtifactKind = Literal[
    "source_document",
    "docling_extraction",
    "normalized_document",
    "alignment",
    "reviewed_alignment",
    "engineering_construction_contract",
    "engineering_document",
    "markdown_export",
    "doorstop_export",
]


class ArtifactReference(BaseModel):
    """Stable identity and optional location of one pipeline artifact."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(pattern=r"^artifact:[a-z_]+:[0-9a-f]{16}$")
    kind: ArtifactKind
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    location: str | None = None
    media_type: str | None = None


class ArtifactLineage(BaseModel):
    """Direct ancestry of one artifact, with deterministic identities."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    artifact: ArtifactReference
    derived_from: tuple[ArtifactReference, ...] = ()
    transformation_ids: tuple[str, ...] = ()


def artifact_reference(
    kind: ArtifactKind,
    payload: Any,
    *,
    location: str | None = None,
    media_type: str | None = None,
) -> ArtifactReference:
    """Build a stable artifact reference from canonical JSON-compatible content."""
    content_hash = canonical_content_hash(payload)
    return ArtifactReference(
        id=f"artifact:{kind}:{content_hash[:16]}",
        kind=kind,
        content_hash=content_hash,
        location=location,
        media_type=media_type,
    )


def canonical_content_hash(payload: Any) -> str:
    """Hash Pydantic models or JSON-compatible payloads deterministically."""
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json", exclude={"lineage"})
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
