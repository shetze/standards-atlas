"""Importer port for engineering documents."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from standards_atlas.domain.model import EngineeringDocument


class EngineeringDocumentImporter(Protocol):
    """Port for adapters that can import engineering documents."""

    def import_document(
        self,
        source: Path,
    ) -> EngineeringDocument:
        """Import an engineering document."""
        ...
