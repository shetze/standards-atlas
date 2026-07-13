"""Reproducible configuration for the Docling PDF pipeline."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DoclingConversionOptions(BaseModel):
    """Stable subset of Docling options used by Standards Atlas."""

    model_config = ConfigDict(frozen=True)

    enable_ocr: bool = False
    extract_tables: bool = True
    extract_pictures: bool = True
    generate_page_images: bool = False

    def as_metadata(self) -> dict[str, bool]:
        """Return a JSON-compatible representation for conversion metadata."""
        return self.model_dump(mode="json")
