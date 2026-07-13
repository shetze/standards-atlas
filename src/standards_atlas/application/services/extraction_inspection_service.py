"""Quality inspection for adapter-neutral extracted documents."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from standards_atlas.application.model import ExtractedDocument


class ExtractionStatistics(BaseModel):
    """Summary of extraction coverage and supported item types."""

    model_config = ConfigDict(frozen=True)

    page_count: int
    item_count: int
    items_with_page_evidence: int
    items_without_page_evidence: int
    unknown_item_count: int
    counts_by_type: dict[str, int]
    unknown_labels: tuple[str, ...]


class ExtractionInspectionService:
    """Calculate deterministic diagnostics for an extracted document."""

    def inspect(self, document: ExtractedDocument) -> ExtractionStatistics:
        counts: dict[str, int] = {}
        pages: set[int] = set()
        with_page = 0
        unknown_labels: set[str] = set()

        for item in document.items:
            counts[item.type] = counts.get(item.type, 0) + 1
            item_pages = {
                evidence.page_number
                for evidence in item.source_evidence
                if evidence.page_number is not None
            }
            if item_pages:
                with_page += 1
                pages.update(item_pages)
            if item.type == "unknown" and item.original_label:
                unknown_labels.add(item.original_label)

        item_count = len(document.items)
        return ExtractionStatistics(
            page_count=len(pages),
            item_count=item_count,
            items_with_page_evidence=with_page,
            items_without_page_evidence=item_count - with_page,
            unknown_item_count=counts.get("unknown", 0),
            counts_by_type=dict(sorted(counts.items())),
            unknown_labels=tuple(sorted(unknown_labels)),
        )
