"""Exporter port for engineering documents."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from standards_atlas.domain.model import EngineeringDocument

class EngineeringDocumentExporter(Protocol):

    def export_document(
        self,
        document: EngineeringDocument,
        target: Path,
    ) -> None:
        ...
