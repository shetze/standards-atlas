"""Application service for updating AtlasData TOC sections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from standards_atlas.application.ports import (
    AtlasDataDocumentReader,
    AtlasDataRoundTripWriterPort,
)


class AtlasDataTocService:
    """Generate and update TOC sections in legacy AtlasData files."""

    def __init__(
        self,
        reader: AtlasDataDocumentReader,
        writer: AtlasDataRoundTripWriterPort,
    ) -> None:
        self._reader = reader
        self._writer = writer

    def update_toc(
        self,
        source: Path,
        *,
        write: bool = False,
    ) -> Any:
        """Generate and optionally write the TOC records for an AtlasData file."""
        document = self._reader.import_document(source)

        return self._writer.update_toc(
            source,
            document,
            write=write,
        )
