from pathlib import Path

from standards_atlas.adapters.docling import DoclingArtifactRepository
from standards_atlas.adapters.docling.extracted_document_repository import (
    DoclingExtractedDocumentRepository,
)
from standards_atlas.application.model import ExtractedDocument, ExtractionMetadata


class StubReader:
    def __init__(self, document: ExtractedDocument) -> None:
        self.document = document

    def read(self, source: Path) -> ExtractedDocument:
        return self.document


class RecordingFormulaVisuals:
    def __init__(self) -> None:
        self.source_pdf: Path | None = None

    def enrich(self, document: ExtractedDocument, source_pdf: Path) -> ExtractedDocument:
        self.source_pdf = source_pdf
        return document


def test_repository_enriches_from_persisted_source_pdf_path(tmp_path: Path) -> None:
    artifacts = DoclingArtifactRepository(tmp_path / ".atlas")
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"%PDF-stub")
    artifacts.save_metadata("STD", {"source_path": str(source_pdf)})
    document = ExtractedDocument(
        source_id="STD",
        metadata=ExtractionMetadata(converter="docling"),
    )
    visuals = RecordingFormulaVisuals()
    repository = DoclingExtractedDocumentRepository(
        artifacts,
        reader=StubReader(document),
        formula_visuals=visuals,
    )

    result = repository.load("STD")

    assert result is document
    assert visuals.source_pdf == source_pdf


def test_repository_skips_visual_enrichment_when_source_is_unavailable(tmp_path: Path) -> None:
    artifacts = DoclingArtifactRepository(tmp_path / ".atlas")
    artifacts.save_metadata("STD", {"source_path": str(tmp_path / "missing.pdf")})
    document = ExtractedDocument(
        source_id="STD",
        metadata=ExtractionMetadata(converter="docling"),
    )
    visuals = RecordingFormulaVisuals()
    repository = DoclingExtractedDocumentRepository(
        artifacts,
        reader=StubReader(document),
        formula_visuals=visuals,
    )

    result = repository.load("STD")

    assert result is document
    assert visuals.source_pdf is None
