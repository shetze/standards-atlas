"""Exporter port for runtime publication documents."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from standards_atlas.application.model import PublicationDocument


class PublicationDocumentExporter(Protocol):
    """Port for adapters that export publication read models."""

    def export_document(
        self,
        document: PublicationDocument,
        target: Path,
        *,
        link_targets: Mapping[tuple[str, str], str] | None = None,
    ) -> Path:
        """Export a publication document and return the generated target path."""
        ...
