# adapters/atlasdata/importer.py

from pathlib import Path

from standards_atlas.adapters.atlasdata.import_pipeline import AtlasDataImportPipeline
from standards_atlas.domain.model import EngineeringDocument


class AtlasDataImporter:
    """Public AtlasData import adapter."""

    def __init__(self, pipeline: AtlasDataImportPipeline | None = None) -> None:
        self._pipeline = pipeline or AtlasDataImportPipeline()

    def import_document(self, source: Path) -> EngineeringDocument:
        return self._pipeline.import_file(source)
