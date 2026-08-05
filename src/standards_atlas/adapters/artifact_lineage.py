"""Write deterministic lineage manifests for exported artifacts."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.domain.model import (
    ArtifactKind,
    ArtifactLineage,
    ArtifactReference,
    EngineeringDocument,
    artifact_reference,
)
from standards_atlas.shared.artifacts import write_json
from standards_atlas.shared.hashing import sha256_file


def write_file_lineage_manifest(
    output: Path,
    document: EngineeringDocument,
    *,
    kind: ArtifactKind,
    media_type: str,
) -> Path:
    """Write a manifest beside one exported file and return its path."""
    artifact = artifact_reference(
        kind,
        {"path": output.name, "sha256": _file_hash(output)},
        location=str(output),
        media_type=media_type,
    )
    lineage = ArtifactLineage(
        artifact=artifact,
        derived_from=_document_parent(document),
    )
    manifest = output.with_suffix(output.suffix + ".lineage.json")
    _write_manifest(manifest, lineage)
    return manifest


def write_directory_lineage_manifest(
    output: Path,
    document: EngineeringDocument,
    *,
    kind: ArtifactKind,
) -> Path:
    """Write a manifest inside an exported directory."""
    files = [
        {"path": str(path.relative_to(output)), "sha256": _file_hash(path)}
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "lineage.json"
    ]
    artifact = artifact_reference(
        kind,
        files,
        location=str(output),
    )
    lineage = ArtifactLineage(
        artifact=artifact,
        derived_from=_document_parent(document),
    )
    manifest = output / "lineage.json"
    _write_manifest(manifest, lineage)
    return manifest


def _document_parent(document: EngineeringDocument) -> tuple[ArtifactReference, ...]:
    return (document.lineage.artifact,) if document.lineage is not None else ()


def _file_hash(path: Path) -> str:
    return sha256_file(path)


def _write_manifest(path: Path, lineage: ArtifactLineage) -> None:
    write_json(path, lineage.model_dump(mode="json"))
