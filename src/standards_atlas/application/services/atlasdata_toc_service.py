"""Application service for updating AtlasData TOC sections."""

from __future__ import annotations

from pathlib import Path

from standards_atlas.adapters.atlasdata import AtlasDataReader
from standards_atlas.adapters.atlasdata.roundtrip_writer import (
    AtlasDataRoundTripResult,
    AtlasDataRoundTripWriter,
)


class AtlasDataTocService:
    """Generate and update TOC sections in legacy AtlasData files."""

    def __init__(
        self,
        reader: AtlasDataReader | None = None,
        writer: AtlasDataRoundTripWriter | None = None,
    ) -> None:
        self._reader = reader or AtlasDataReader()
        self._writer = writer or AtlasDataRoundTripWriter()

    def update_toc(
        self,
        source: Path,
        *,
        write: bool = False,
    ) -> AtlasDataRoundTripResult:
        """Generate and optionally write the TOC records for an AtlasData file."""
        document = self._reader.import_document(source)

        return self._writer.update_toc(
            source,
            document,
            write=write,
        )
