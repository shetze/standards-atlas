"""High-level Atlas Data import pipeline."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.atlasdata.domain_mapper import map_atlas_data_to_standard
from standards_atlas.adapters.atlasdata.parser import AtlasStandardData, parse_standard_file
from standards_atlas.domain.model import EngineeringDocument


class AtlasDataImporter:
    """Import legacy Atlas data files into the canonical domain model."""

    def import_file(self, source: Path, *, key: str | None = None) -> EngineeringDocument:
        """Import an Atlas data file."""
        atlas_data = self.parse_file(source)
        document_key = key or source.name

        return self.map_to_domain(atlas_data, key=document_key)

    def parse_file(self, source: Path) -> AtlasStandardData:
        """Parse an Atlas data file into the adapter-internal representation."""
        return parse_standard_file(source)

    def map_to_domain(self, atlas_data: AtlasStandardData, *, key: str) -> EngineeringDocument:
        """Map parsed Atlas data into the canonical domain model."""
        return map_atlas_data_to_standard(atlas_data, key=key)
