"""Optional Docling PDF extraction adapter."""

from standards_atlas.adapters.docling.converter import DoclingPdfConverter
from standards_atlas.adapters.docling.document_reader import DoclingJsonReader
from standards_atlas.adapters.docling.errors import (
    DoclingAdapterError,
    DoclingDocumentValidationError,
    DoclingNotInstalledError,
    DocumentConversionError,
)
from standards_atlas.adapters.docling.options import DoclingConversionOptions
from standards_atlas.adapters.docling.repository import (
    DoclingArtifactRepository,
    ExtractionState,
    sha256_file,
)

__all__ = [
    "DoclingAdapterError",
    "DoclingArtifactRepository",
    "DoclingConversionOptions",
    "DoclingDocumentValidationError",
    "DoclingJsonReader",
    "DoclingNotInstalledError",
    "DoclingPdfConverter",
    "DocumentConversionError",
    "ExtractionState",
    "sha256_file",
]
