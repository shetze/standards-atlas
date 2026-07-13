"""Port for converting source documents into adapter-native representations."""

from pathlib import Path
from typing import Protocol


class DocumentConverter(Protocol):
    """Convert a source file and persist the adapter-native result."""

    def convert(self, source: Path, target: Path, *, overwrite: bool = False) -> Path:
        """Convert ``source`` and return the persisted native representation."""
