"""Enrich canonical engineering documents with aligned normalized content."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from standards_atlas.adapters.alignment import AlignmentArtifactRepository
from standards_atlas.adapters.alignment_review import AlignmentReviewRepository
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.application.model.alignment import (
    AlignmentResult,
    AlignmentStatus,
    ClauseAlignment,
)
from standards_atlas.application.model.normalized_document import (
    NormalizedCode,
    NormalizedExtractedDocument,
    NormalizedFormula,
    NormalizedHeading,
    NormalizedItem,
    NormalizedList,
    NormalizedListItem,
    NormalizedPicture,
    NormalizedTable,
    NormalizedText,
    NormalizedUnknown,
)
from standards_atlas.domain.model import (
    ArtifactLineage,
    Clause,
    CodeBlock,
    ContentBlock,
    DocumentKey,
    EngineeringDocument,
    FormulaBlock,
    ListBlock,
    ListItem,
    PictureBlock,
    TableBlock,
    TextBlock,
    artifact_reference,
)


class ContentEnrichmentError(ValueError):
    """Raised when aligned content cannot be enriched safely."""


class ContentEnrichmentStatistics(BaseModel):
    """Summary of one deterministic content-enrichment run."""

    model_config = ConfigDict(frozen=True)

    clauses_total: int
    clauses_enriched: int
    clauses_empty: int
    content_blocks: int
    normalized_items_consumed: int
    used_reviewed_alignment: bool


class ContentEnrichmentResult(BaseModel):
    """Result returned after persisting an enriched document."""

    model_config = ConfigDict(frozen=True)

    document: EngineeringDocument
    statistics: ContentEnrichmentStatistics


class ContentEnrichmentService:
    """Partition aligned normalized content into canonical clause blocks."""

    def __init__(self, workspace: Path = Path(".atlas")) -> None:
        self._documents = FileSystemEngineeringDocumentRepository(workspace)
        self._normalized = NormalizationArtifactRepository(workspace)
        self._alignments = AlignmentArtifactRepository(workspace)
        self._reviews = AlignmentReviewRepository(workspace)

    def enrich(
        self,
        document_key: str,
        *,
        prefer_reviewed: bool = True,
        allow_unresolved: bool = False,
    ) -> ContentEnrichmentResult:
        """Populate ``Clause.content`` and persist the canonical document.

        Reviewed alignment is preferred when available. Automatic alignment is
        otherwise used. Missing, ambiguous or conflicting clauses abort the
        operation unless ``allow_unresolved`` is explicitly enabled.
        """
        key = DocumentKey(value=document_key)
        document = self._documents.load(key)
        normalized = self._normalized.load(document_key)
        alignment, used_reviewed = self._load_alignment(
            document_key,
            prefer_reviewed=prefer_reviewed,
        )
        self._validate_sources(document, normalized, alignment)
        self._validate_alignment(alignment, allow_unresolved=allow_unresolved)

        alignments_by_clause = {entry.clause_id: entry for entry in alignment.clauses}
        items_by_sequence = {item.sequence_number: item for item in normalized.items}

        enriched_clauses: list[Clause] = []
        enriched_count = 0
        empty_count = 0
        block_count = 0
        consumed_item_ids: set[str] = set()

        for clause in document.clauses:
            clause_alignment = alignments_by_clause.get(clause.id.value)
            if clause_alignment is None or clause_alignment.start_sequence_number is None:
                enriched_clauses.append(clause)
                empty_count += 1
                continue

            items = _items_for_alignment(clause_alignment, items_by_sequence)
            blocks, consumed = _content_blocks(clause_alignment, items)
            consumed_item_ids.update(consumed)
            block_count += len(blocks)
            if blocks:
                enriched_count += 1
            else:
                empty_count += 1
            enriched_clauses.append(
                clause.model_copy(
                    update={
                        "title": _enriched_title(clause, clause_alignment),
                        "content": blocks,
                        "text": None,
                    }
                )
            )

        draft = document.model_copy(update={"clauses": tuple(enriched_clauses)})
        parent_artifacts = []
        if document.lineage is not None:
            parent_artifacts.append(document.lineage.artifact)
        if normalized.lineage is not None:
            parent_artifacts.append(normalized.lineage.artifact)
        enriched = draft.model_copy(
            update={
                "lineage": ArtifactLineage(
                    artifact=artifact_reference("engineering_document", draft),
                    derived_from=tuple(parent_artifacts),
                )
            }
        )
        self._documents.save(enriched)
        return ContentEnrichmentResult(
            document=enriched,
            statistics=ContentEnrichmentStatistics(
                clauses_total=len(document.clauses),
                clauses_enriched=enriched_count,
                clauses_empty=empty_count,
                content_blocks=block_count,
                normalized_items_consumed=len(consumed_item_ids),
                used_reviewed_alignment=used_reviewed,
            ),
        )

    def _load_alignment(
        self,
        document_key: str,
        *,
        prefer_reviewed: bool,
    ) -> tuple[AlignmentResult, bool]:
        reviewed_path = self._reviews.reviewed_path(document_key)
        if prefer_reviewed and reviewed_path.exists():
            return self._reviews.load_reviewed(document_key), True
        return self._alignments.load(document_key), False

    @staticmethod
    def _validate_sources(
        document: EngineeringDocument,
        normalized: NormalizedExtractedDocument,
        alignment: AlignmentResult,
    ) -> None:
        if alignment.source_id != normalized.source_id:
            raise ContentEnrichmentError(
                "Alignment and normalized document use different source identifiers."
            )
        clause_ids = {clause.id.value for clause in document.clauses}
        unknown = [
            entry.clause_id for entry in alignment.clauses if entry.clause_id not in clause_ids
        ]
        if unknown:
            raise ContentEnrichmentError(
                "Alignment contains clauses not present in the engineering document: "
                + ", ".join(unknown[:5])
            )

    @staticmethod
    def _validate_alignment(
        alignment: AlignmentResult,
        *,
        allow_unresolved: bool,
    ) -> None:
        unresolved = [
            entry
            for entry in alignment.clauses
            if entry.status
            in {
                AlignmentStatus.MISSING,
                AlignmentStatus.AMBIGUOUS,
                AlignmentStatus.CONFLICTING,
            }
        ]
        if unresolved and not allow_unresolved:
            references = ", ".join(entry.expected_reference for entry in unresolved[:10])
            raise ContentEnrichmentError(
                f"Alignment contains {len(unresolved)} unresolved clauses: {references}. "
                "Complete review or pass --allow-unresolved."
            )


def _items_for_alignment(
    alignment: ClauseAlignment,
    items_by_sequence: dict[int, NormalizedItem],
) -> tuple[NormalizedItem, ...]:
    if alignment.start_sequence_number is None or alignment.end_sequence_number is None:
        return ()
    return tuple(
        items_by_sequence[sequence]
        for sequence in range(
            alignment.start_sequence_number,
            alignment.end_sequence_number + 1,
        )
        if sequence in items_by_sequence
    )


def _content_blocks(
    alignment: ClauseAlignment,
    items: tuple[NormalizedItem, ...],
) -> tuple[tuple[ContentBlock, ...], set[str]]:
    blocks: list[ContentBlock] = []
    consumed: set[str] = set()
    for index, item in enumerate(items):
        consumed.add(item.id)
        if item.id == alignment.following_label_item_id:
            continue
        block = _item_to_block(item, alignment=alignment, is_first=index == 0)
        if block is not None:
            blocks.append(block)
    return tuple(blocks), consumed


def _item_to_block(
    item: NormalizedItem,
    *,
    alignment: ClauseAlignment,
    is_first: bool,
):
    if isinstance(item, (NormalizedText, NormalizedHeading)):
        text = item.text
        if is_first:
            text = _first_item_content(alignment, item)
        if not text or not text.strip():
            return None
        return TextBlock(
            id=f"content:{item.id}",
            text=text.strip(),
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedList):
        return ListBlock(
            id=f"content:{item.id}",
            ordered=item.ordered,
            items=tuple(_list_item(value) for value in item.items),
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedTable):
        return TableBlock(
            id=f"content:{item.id}",
            rows=item.rows,
            caption=item.caption,
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedPicture):
        return PictureBlock(
            id=f"content:{item.id}",
            caption=item.caption,
            image_path=item.image_reference,
            description=item.description,
            media_type=item.visual_asset.media_type if item.visual_asset else None,
            content_hash=item.visual_asset.content_hash if item.visual_asset else None,
            embedded_data_uri=item.visual_asset.data_uri if item.visual_asset else None,
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedFormula):
        return FormulaBlock(
            id=f"content:{item.id}",
            expression=item.expression,
            original_expression=item.original_expression,
            representation=item.representation,
            extraction_status=item.extraction_status,
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedCode):
        return CodeBlock(
            id=f"content:{item.id}",
            code=item.code,
            language=item.language,
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedUnknown) and item.text and item.text.strip():
        return TextBlock(
            id=f"content:{item.id}",
            text=item.text.strip(),
            source_evidence=item.source_evidence,
        )

    return None


def _first_item_content(alignment: ClauseAlignment, item: NormalizedItem) -> str | None:
    """Remove the structural clause head while retaining inline clause text."""
    if alignment.remainder_kind and alignment.remainder_kind.value == "content":
        return alignment.observed_remainder
    if alignment.remainder_kind and alignment.remainder_kind.value in {"title", "unknown"}:
        return None
    # Inferred ranges have no proven structural head. Preserve their first item
    # rather than discarding protected content based on an unsupported guess.
    return getattr(item, "text", None)


def _list_item(item: NormalizedListItem) -> ListItem:
    return ListItem(
        text=item.text,
        ordered=item.ordered,
        children=tuple(_list_item(child) for child in item.children),
    )


def _enriched_title(clause: Clause, alignment: ClauseAlignment) -> str | None:
    """Prefer a detected heading and retain the AtlasData fallback otherwise."""
    if (
        alignment.remainder_kind
        and alignment.remainder_kind.value == "title"
        and alignment.observed_remainder
        and alignment.observed_remainder.strip()
    ):
        return alignment.observed_remainder.strip()
    return clause.title
