"""Export a logical standard family to one Markdown file per physical part."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from standards_atlas.application.analysis import (
    resolve_cross_document_reference_relations,
)
from standards_atlas.application.ports import (
    EngineeringDocumentExporter,
    PublicationDocumentReader,
)
from standards_atlas.domain.model import DocumentKey, EngineeringDocument


@dataclass(frozen=True)
class MarkdownExportResult:
    document_key: str
    generated_files: tuple[Path, ...]
    clauses_exported: int


class MarkdownExportService:
    """Split multi-part documents by volume and export them in one invocation."""

    def __init__(
        self,
        exporter: EngineeringDocumentExporter,
        documents: PublicationDocumentReader,
    ) -> None:
        self._exporter = exporter
        self._documents = documents

    def export(
        self,
        document_key: str,
        target_directory: Path,
        *,
        replace_existing: bool = True,
    ) -> MarkdownExportResult:
        document = self._documents.load(DocumentKey(value=document_key))
        available_documents = self._documents.list()
        document = resolve_cross_document_reference_relations(
            document,
            available_documents,
        )
        target_directory.mkdir(parents=True, exist_ok=True)
        parts = _split_document(document)
        target_paths = _target_paths_for_parts(document, parts, target_directory)
        all_clause_targets = _build_clause_target_index(
            current_document=document,
            current_target_directory=target_directory,
            available_documents=available_documents,
        )

        generated: list[Path] = []
        for (volume, part), target in zip(parts, target_paths, strict=True):
            del volume
            if target.exists() and not replace_existing:
                raise FileExistsError(f"Markdown target already exists: {target}")
            link_targets = _relative_link_targets(target, all_clause_targets)
            generated.append(
                self._exporter.export_document(
                    part,
                    target,
                    link_targets=link_targets,
                )
            )
        return MarkdownExportResult(
            document.key.value,
            tuple(generated),
            sum(len(part.clauses) for _, part in parts),
        )


def _build_clause_target_index(
    *,
    current_document: EngineeringDocument,
    current_target_directory: Path,
    available_documents: tuple[EngineeringDocument, ...],
) -> dict[tuple[str, str], tuple[Path, str]]:
    export_root = current_target_directory.parent
    index: dict[tuple[str, str], tuple[Path, str]] = {}
    for document in available_documents:
        target_directory = (
            current_target_directory
            if document.key == current_document.key
            else export_root / _safe_filename(document.key.value)
        )
        parts = _split_document(document)
        paths = _target_paths_for_parts(document, parts, target_directory)
        for (_volume, part), path in zip(parts, paths, strict=True):
            for clause in part.clauses:
                index[(document.key.value, clause.id.value)] = (
                    path,
                    clause.reference.clause,
                )
    return index


def _relative_link_targets(
    source_target: Path,
    clause_targets: dict[tuple[str, str], tuple[Path, str]],
) -> dict[tuple[str, str], str]:
    links: dict[tuple[str, str], str] = {}
    for key, (path, reference) in clause_targets.items():
        relative_path = Path(os.path.relpath(path, start=source_target.parent)).as_posix()
        links[key] = f"{relative_path}#clause-{_anchor(reference)}"
    return links


def _target_paths_for_parts(
    document: EngineeringDocument,
    parts: tuple[tuple[str | None, EngineeringDocument], ...],
    target_directory: Path,
) -> tuple[Path, ...]:
    targets = []
    for volume, _part in parts:
        suffix = f"-{_safe_filename(volume)}" if volume is not None else ""
        targets.append(target_directory / f"{_safe_filename(document.key.value)}{suffix}.md")
    return tuple(targets)


def _split_document(
    document: EngineeringDocument,
) -> tuple[tuple[str | None, EngineeringDocument], ...]:
    volumes = sorted(
        {clause.reference.part for clause in document.clauses if clause.reference.part},
        key=_natural_key,
    )
    if not volumes:
        return ((None, document),)
    parts: list[tuple[str | None, EngineeringDocument]] = []
    for volume in volumes:
        clauses = tuple(
            clause
            for clause in document.clauses
            if clause.reference.part == volume and clause.reference.clause.strip() != "0"
        )
        clause_ids = {c.id for c in clauses}
        annotations = tuple(a for a in document.annotations if a.clause_id in clause_ids)
        title = (
            document.title
            if document.title.rstrip().endswith(f"-{volume}")
            else f"{document.title}-{volume}"
        )
        parts.append(
            (
                volume,
                document.model_copy(
                    update={
                        "title": title,
                        "clauses": clauses,
                        "annotations": annotations,
                    }
                ),
            )
        )
    return tuple(parts)


def _natural_key(value: str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)
    )


def _anchor(reference: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", reference.casefold()).strip("-")


def _safe_filename(value: str) -> str:
    return value.strip().replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
