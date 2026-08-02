"""Exporter port for engineering documents."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from standards_atlas.domain.model import EngineeringDocument


class EngineeringDocumentExporter(Protocol):
    """Port for adapters that export engineering documents."""

    def export_document(
        self,
        document: EngineeringDocument,
        target: Path,
        *,
        link_targets: Mapping[tuple[str, str], str] | None = None,
    ) -> Path:
        """Export a document and return the generated target path."""
        ...
