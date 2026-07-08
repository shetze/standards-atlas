"""Writer port for engineering documents."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from standards_atlas.domain.model import EngineeringDocument


class EngineeringDocumentWriter(Protocol):
    """Port for adapters that can write engineering documents."""

    def write_document(
        self,
        document: EngineeringDocument,
        target: Path,
    ) -> None:
        """Write an engineering document to an external target."""
        ...
