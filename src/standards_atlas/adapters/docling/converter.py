"""Docling-backed PDF conversion adapter."""

from __future__ import annotations

import importlib.metadata
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from standards_atlas.adapters.docling.errors import (
    DoclingNotInstalledError,
    DocumentConversionError,
)
from standards_atlas.adapters.docling.options import (
    DoclingAcceleratorDevice,
    DoclingConversionOptions,
)
from standards_atlas.adapters.docling.repository import sha256_file


class DoclingPdfConverter:
    """Convert PDFs into native, lossless Docling JSON documents."""

    def __init__(self, options: DoclingConversionOptions | None = None) -> None:
        self._options = options or DoclingConversionOptions()

    @property
    def options(self) -> DoclingConversionOptions:
        """Return the reproducible conversion options."""
        return self._options

    def convert(self, source: Path, target: Path, *, overwrite: bool = False) -> Path:
        """Convert ``source`` and atomically persist native Docling JSON."""
        if source.suffix.lower() != ".pdf":
            raise DocumentConversionError(f"Docling PDF adapter requires a PDF source: {source}")
        if not source.is_file():
            raise FileNotFoundError(source)
        if target.exists() and not overwrite:
            raise FileExistsError(f"Docling document already exists: {target}")

        document_converter = _create_document_converter(self._options)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")

        try:
            result = document_converter.convert(source)
            document = getattr(result, "document", None)
            if document is None:
                raise DocumentConversionError("Docling conversion returned no document")
            document.save_as_json(temporary)
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise DocumentConversionError("Docling produced an empty native document")
            os.replace(temporary, target)
        except (FileExistsError, DocumentConversionError):
            temporary.unlink(missing_ok=True)
            raise
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            temporary.unlink(missing_ok=True)
            raise DocumentConversionError(f"Docling failed to convert {source}: {exc}") from exc

        return target

    def conversion_metadata(self, source: Path) -> dict[str, Any]:
        """Build reproducibility metadata for a completed conversion."""
        try:
            version = importlib.metadata.version("docling")
        except importlib.metadata.PackageNotFoundError:
            version = None
        return {
            "schema_version": 1,
            "converter": "docling",
            "converter_version": version,
            "created_at": datetime.now(UTC).isoformat(),
            "source_path": str(source.resolve()),
            "source_sha256": sha256_file(source),
            "source_size": source.stat().st_size,
            "options": self._options.as_metadata(),
        }


def _create_document_converter(options: DoclingConversionOptions) -> Any:
    try:
        from docling.datamodel.accelerator_options import (
            AcceleratorDevice,
            AcceleratorOptions,
        )
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise DoclingNotInstalledError(
            "Docling support is not installed. Install it with: "
            'pip install "standards-atlas[docling]"'
        ) from exc

    device_mapping = {
        DoclingAcceleratorDevice.AUTO: AcceleratorDevice.AUTO,
        DoclingAcceleratorDevice.CPU: AcceleratorDevice.CPU,
        DoclingAcceleratorDevice.CUDA: AcceleratorDevice.CUDA,
        DoclingAcceleratorDevice.MPS: AcceleratorDevice.MPS,
        DoclingAcceleratorDevice.XPU: AcceleratorDevice.XPU,
    }

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = options.enable_ocr
    pipeline_options.do_table_structure = options.extract_tables
    pipeline_options.generate_picture_images = options.extract_pictures
    pipeline_options.generate_page_images = options.generate_page_images
    pipeline_options.accelerator_options = AcceleratorOptions(
        device=device_mapping[options.accelerator_device],
        num_threads=options.accelerator_threads,
    )
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )
