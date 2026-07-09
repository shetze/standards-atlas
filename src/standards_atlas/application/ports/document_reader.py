"""Reader port for engineering documents."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from standards_atlas.domain.model import EngineeringDocument


class EngineeringDocumentReader(Protocol):
    """Port for adapters that can read engineering documents."""

    def import_document(self, source: Path) -> EngineeringDocument:
        """Read an engineering document from an external source."""
        ...
