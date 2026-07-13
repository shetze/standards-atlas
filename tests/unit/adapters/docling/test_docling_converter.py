from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from standards_atlas.adapters.docling import (
    DoclingConversionOptions,
    DocumentConversionError,
)
from standards_atlas.adapters.docling.converter import DoclingPdfConverter


def test_converter_rejects_non_pdf_sources(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("not a PDF", encoding="utf-8")

    with pytest.raises(DocumentConversionError, match="requires a PDF"):
        DoclingPdfConverter().convert(source, tmp_path / "document.json")


def test_converter_rejects_missing_pdf(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        DoclingPdfConverter().convert(
            tmp_path / "missing.pdf",
            tmp_path / "document.json",
        )


def test_converter_does_not_replace_existing_artifact_without_permission(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-test")
    target = tmp_path / "document.json"
    target.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        DoclingPdfConverter().convert(source, target)


def test_conversion_metadata_records_options_and_source_identity(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-test")
    options = DoclingConversionOptions(enable_ocr=True, generate_page_images=True)

    metadata = DoclingPdfConverter(options).conversion_metadata(source)

    assert metadata["schema_version"] == 1
    assert metadata["converter"] == "docling"
    assert metadata["source_path"] == str(source.resolve())
    assert metadata["source_size"] == len(b"%PDF-test")
    assert len(metadata["source_sha256"]) == 64
    assert metadata["created_at"]
    assert metadata["options"] == options.as_metadata()


def test_converter_wraps_runtime_failure_and_removes_temporary_file(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-test")
    target = tmp_path / "document.json"
    converter = Mock()
    converter.convert.side_effect = RuntimeError("pipeline failed")

    with patch(
        "standards_atlas.adapters.docling.converter._create_document_converter",
        return_value=converter,
    ):
        with pytest.raises(DocumentConversionError, match="pipeline failed"):
            DoclingPdfConverter().convert(source, target)

    assert not target.exists()
    assert not target.with_suffix(".json.tmp").exists()
