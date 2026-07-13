from pathlib import Path

from standards_atlas.application.model import ExtractedDocument, ExtractionMetadata
from standards_atlas.application.services import DocumentExtractionService


class FakeConverter:
    def convert(self, source: Path, target: Path, *, overwrite: bool = False) -> Path:
        target.write_text("{}", encoding="utf-8")
        return target


class FakeReader:
    def read(self, source: Path) -> ExtractedDocument:
        return ExtractedDocument(
            source_id=source.stem,
            metadata=ExtractionMetadata(converter="fake"),
        )


def test_service_keeps_conversion_and_neutral_reading_separate(tmp_path: Path) -> None:
    target = tmp_path / "document.json"
    result = DocumentExtractionService(FakeConverter(), FakeReader()).convert_and_read(
        tmp_path / "source.pdf",
        target,
    )

    assert target.exists()
    assert result.source_id == "document"
    assert result.metadata.converter == "fake"
