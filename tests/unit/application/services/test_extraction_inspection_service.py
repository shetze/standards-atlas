from standards_atlas.application.model import (
    ExtractedDocument,
    ExtractedText,
    ExtractedUnknown,
    ExtractionMetadata,
)
from standards_atlas.application.services import ExtractionInspectionService
from standards_atlas.domain.model import SourceEvidence


def test_inspection_reports_coverage_and_unknown_labels() -> None:
    document = ExtractedDocument(
        source_id="STD",
        metadata=ExtractionMetadata(converter="docling"),
        items=(
            ExtractedText(
                id="text-1",
                sequence_number=0,
                text="Content",
                source_evidence=(
                    SourceEvidence(
                        source_id="STD",
                        source_type="pdf",
                        page_number=1,
                    ),
                ),
            ),
            ExtractedUnknown(
                id="unknown-1",
                sequence_number=1,
                original_label="custom",
                text="Unknown content",
            ),
        ),
    )

    statistics = ExtractionInspectionService().inspect(document)

    assert statistics.page_count == 1
    assert statistics.item_count == 2
    assert statistics.items_with_page_evidence == 1
    assert statistics.items_without_page_evidence == 1
    assert statistics.unknown_item_count == 1
    assert statistics.counts_by_type == {"text": 1, "unknown": 1}
    assert statistics.unknown_labels == ("custom",)
