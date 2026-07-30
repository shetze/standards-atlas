"""Optional Docling PDF extraction adapter."""

from standards_atlas.adapters.docling.converter import DoclingPdfConverter
from standards_atlas.adapters.docling.document_reader import DoclingJsonReader
from standards_atlas.adapters.docling.errors import (
    DoclingAdapterError,
    DoclingDocumentValidationError,
    DoclingNotInstalledError,
    DocumentConversionError,
)
from standards_atlas.adapters.docling.extracted_document_repository import (
    DoclingExtractedDocumentRepository,
)
from standards_atlas.adapters.docling.options import (
    DoclingAcceleratorDevice,
    DoclingConversionOptions,
)
from standards_atlas.adapters.docling.repository import (
    DoclingArtifactRepository,
    ExtractionState,
    sha256_file,
)

__all__ = [
    "DoclingAdapterError",
    "DoclingAcceleratorDevice",
    "DoclingArtifactRepository",
    "DoclingExtractedDocumentRepository",
    "DoclingConversionOptions",
    "DoclingDocumentValidationError",
    "DoclingJsonReader",
    "DoclingNotInstalledError",
    "DoclingPdfConverter",
    "DocumentConversionError",
    "ExtractionState",
    "sha256_file",
]
