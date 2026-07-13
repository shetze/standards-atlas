"""Errors raised by the optional Docling adapter."""


class DoclingAdapterError(RuntimeError):
    """Base class for Docling integration failures."""


class DoclingNotInstalledError(DoclingAdapterError):
    """Raised when PDF conversion is requested without the optional dependency."""


class DocumentConversionError(DoclingAdapterError):
    """Raised when Docling cannot convert a source document."""


class DoclingDocumentValidationError(DoclingAdapterError):
    """Raised when persisted Docling JSON cannot be interpreted."""
