"""Atlas Data reader adapter."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.atlasdata.atlas_importer import AtlasDataImporter
from standards_atlas.domain.model import EngineeringDocument


class AtlasDataReader:
    """Read legacy Atlas data files as engineering documents."""

    def __init__(self, importer: AtlasDataImporter | None = None) -> None:
        self._importer = importer or AtlasDataImporter()

    def import_document(self, source: Path) -> EngineeringDocument:
        """Read an Atlas data file."""
        return self._importer.import_file(source)
