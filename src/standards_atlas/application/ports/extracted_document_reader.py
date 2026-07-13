"""Port for reading adapter-native extraction results."""

from pathlib import Path
from typing import Protocol

from standards_atlas.application.model import ExtractedDocument


class ExtractedDocumentReader(Protocol):
    """Read an extraction into an adapter-neutral application model."""

    def read(self, source: Path) -> ExtractedDocument:
        """Read ``source`` into an ordered extracted document."""
