"""Export a logical standard family to one Markdown file per physical part."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.ports import EngineeringDocumentExporter
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
        workspace: Path = Path(".atlas"),
    ) -> None:
        self._exporter = exporter
        self._documents = FileSystemEngineeringDocumentRepository(workspace)

    def export(
        self,
        document_key: str,
        target_directory: Path,
        *,
        replace_existing: bool = True,
    ) -> MarkdownExportResult:
        document = self._documents.load(DocumentKey(value=document_key))
        target_directory.mkdir(parents=True, exist_ok=True)
        parts = _split_document(document)
        generated: list[Path] = []
        for volume, part in parts:
            suffix = f"-{_safe_filename(volume)}" if volume is not None else ""
            target = target_directory / f"{_safe_filename(document.key.value)}{suffix}.md"
            if target.exists() and not replace_existing:
                raise FileExistsError(f"Markdown target already exists: {target}")
            generated.append(self._exporter.export_document(part, target))
        return MarkdownExportResult(
            document.key.value,
            tuple(generated),
            sum(len(part.clauses) for _, part in parts),
        )


def _split_document(
    document: EngineeringDocument,
) -> tuple[tuple[str | None, EngineeringDocument], ...]:
    volumes = sorted(
        {clause.volume for clause in document.clauses if clause.volume},
        key=_natural_key,
    )
    if not volumes:
        return ((None, document),)
    parts: list[tuple[str | None, EngineeringDocument]] = []
    for volume in volumes:
        clauses = tuple(
            clause
            for clause in document.clauses
            if clause.volume == volume and clause.reference.clause.strip() != "0"
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
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", value)
    )


def _safe_filename(value: str) -> str:
    return value.strip().replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
