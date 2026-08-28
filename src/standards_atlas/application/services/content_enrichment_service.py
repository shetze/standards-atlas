"""Enrich canonical engineering documents with aligned normalized content."""

from __future__ import annotations

import hashlib
import re

from pydantic import BaseModel, ConfigDict

from standards_atlas.application.analysis import resolve_internal_reference_relations
from standards_atlas.application.model.alignment import (
    AlignmentResult,
    AlignmentStatus,
    ClauseAlignment,
)
from standards_atlas.application.model.engineering_construction import (
    EngineeringConstructionContract,
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
from standards_atlas.application.ports import (
    AlignmentReviewStore,
    AlignmentStore,
    EngineeringConstructionContractStore,
    EngineeringDocumentRepository,
    NormalizationRepository,
)
from standards_atlas.application.references import (
    extract_reference_mentions,
    resolve_document_reference_mentions,
)
from standards_atlas.application.services.engineering_construction_contract import (
    EngineeringConstructionContractValidator,
)
from standards_atlas.domain.model import (
    ArtifactLineage,
    Clause,
    CodeBlock,
    ContentBlock,
    DocumentKey,
    DocumentTable,
    DocumentTableId,
    EngineeringDocument,
    FormulaBlock,
    GeneratedAttribute,
    GenerationMethod,
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
    construction_contract: EngineeringConstructionContract


class ContentEnrichmentResult(BaseModel):
    """Result returned after persisting an enriched document."""

    model_config = ConfigDict(frozen=True)

    document: EngineeringDocument
    statistics: ContentEnrichmentStatistics


class ContentEnrichmentService:
    """Partition aligned normalized content into canonical clause blocks."""

    def __init__(
        self,
        documents: EngineeringDocumentRepository,
        normalized: NormalizationRepository,
        alignments: AlignmentStore,
        reviews: AlignmentReviewStore,
        contracts: EngineeringConstructionContractStore,
        contract_validator: EngineeringConstructionContractValidator | None = None,
    ) -> None:
        self._documents = documents
        self._normalized = normalized
        self._alignments = alignments
        self._reviews = reviews
        self._contracts = contracts
        self._contract_validator = contract_validator or EngineeringConstructionContractValidator()

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
        automatic_alignment = self._alignments.load(document_key)
        alignment, used_reviewed = self._load_alignment(
            document_key,
            prefer_reviewed=prefer_reviewed,
        )
        self._validate_sources(document, normalized, alignment)
        self._validate_alignment(alignment, allow_unresolved=allow_unresolved)
        reviewed_integrity_valid = True
        reviewed_integrity_message = None
        if used_reviewed:
            reviewed_integrity_valid, reviewed_integrity_message = self._reviews.verify_reviewed(
                document_key,
                automatic_alignment_hash=self._reviews.hash_alignment(automatic_alignment),
            )
        contract = self._contract_validator.validate(
            normalized,
            alignment,
            automatic_alignment,
            reviewed_alignment_used=used_reviewed,
            reviewed_integrity_valid=reviewed_integrity_valid,
            reviewed_integrity_message=reviewed_integrity_message,
        )
        if not contract.valid:
            codes = ", ".join(
                item.code for item in contract.diagnostics if item.severity == "error"
            )
            raise ContentEnrichmentError(
                f"EngineeringDocument construction contract failed: {codes}"
            )

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
            enriched_clause = clause.with_baseline_updates(
                heading=_enriched_title(clause, clause_alignment),
                content=blocks,
            )
            enriched_clause = enriched_clause.with_baseline_updates(
                reference_mentions=extract_reference_mentions(enriched_clause.plain_text)
            )
            generated = [
                GeneratedAttribute(
                    path="baseline.content",
                    generator="normalized-content-enrichment",
                    method=GenerationMethod.SOURCE_EXTRACTION,
                ),
                GeneratedAttribute(
                    path="baseline.reference_mentions",
                    generator="reference-mention-extractor",
                    method=GenerationMethod.DETERMINISTIC,
                ),
            ]
            if clause.heading is None and enriched_clause.heading is not None:
                generated.append(
                    GeneratedAttribute(
                        path="baseline.heading",
                        generator="normalized-content-enrichment",
                        method=GenerationMethod.SOURCE_EXTRACTION,
                    )
                )
            enriched_clauses.append(enriched_clause.mark_generated(*generated))

        traceability_errors = _content_traceability_errors(tuple(enriched_clauses), normalized)
        if traceability_errors:
            raise ContentEnrichmentError(
                "EngineeringDocument content traceability failed: "
                + "; ".join(traceability_errors[:10])
            )

        enriched_tables, enriched_table_index = _lift_document_tables(
            document, tuple(enriched_clauses)
        )
        draft = document.model_copy(
            update={
                "clauses": tuple(enriched_clauses),
                "tables": enriched_tables,
                "table_index": enriched_table_index,
            }
        )
        draft = resolve_document_reference_mentions(draft)
        resolved_relations = resolve_internal_reference_relations(draft)
        clauses_with_relations = []
        for clause in draft.clauses:
            detected_relations = resolved_relations.get(clause.id.value, ())
            relation_keys = {
                (
                    relation.kind,
                    relation.scope,
                    relation.target_reference,
                    relation.target_document_key,
                    relation.display_text,
                )
                for relation in clause.reference_relations
            }
            merged_relations = list(clause.reference_relations)
            for relation in detected_relations:
                key = (
                    relation.kind,
                    relation.scope,
                    relation.target_reference,
                    relation.target_document_key,
                    relation.display_text,
                )
                if key not in relation_keys:
                    merged_relations.append(relation)
                    relation_keys.add(key)
            updated_clause = clause.with_baseline_updates(
                reference_relations=tuple(merged_relations)
            )
            if tuple(merged_relations) != clause.reference_relations:
                updated_clause = updated_clause.mark_generated(
                    GeneratedAttribute(
                        path="baseline.reference_relations",
                        generator="internal-reference-resolver",
                        method=GenerationMethod.DETERMINISTIC,
                    )
                )
            clauses_with_relations.append(updated_clause)
        draft = draft.model_copy(update={"clauses": tuple(clauses_with_relations)})
        parent_artifacts = []
        if document.lineage is not None:
            parent_artifacts.append(document.lineage.artifact)
        if normalized.lineage is not None:
            parent_artifacts.append(normalized.lineage.artifact)
        alignment_kind = "reviewed_alignment" if used_reviewed else "alignment"
        parent_artifacts.append(artifact_reference(alignment_kind, alignment))
        parent_artifacts.append(artifact_reference("engineering_construction_contract", contract))
        enriched = draft.model_copy(
            update={
                "lineage": ArtifactLineage(
                    artifact=artifact_reference("engineering_document", draft),
                    derived_from=tuple(parent_artifacts),
                )
            }
        )
        self._contracts.save(document_key, contract)
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
                construction_contract=contract,
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
            normalized_item_ids=(item.id,),
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedList):
        return ListBlock(
            id=f"content:{item.id}",
            ordered=item.ordered,
            items=tuple(_list_item(value) for value in item.items),
            normalized_item_ids=(item.id,),
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedTable):
        return TableBlock(
            id=f"content:{item.id}",
            rows=item.rows,
            caption=item.caption,
            normalized_item_ids=(item.id,),
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
            normalized_item_ids=(item.id,),
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedFormula):
        visual_only = item.extraction_status == "visual_only"
        return FormulaBlock(
            id=f"content:{item.id}",
            expression="" if visual_only else item.expression,
            original_expression=None if visual_only else item.original_expression,
            representation=item.representation,
            extraction_status=item.extraction_status,
            media_type=item.visual_asset.media_type if item.visual_asset else None,
            content_hash=item.visual_asset.content_hash if item.visual_asset else None,
            embedded_data_uri=item.visual_asset.data_uri if item.visual_asset else None,
            normalized_item_ids=(item.id,),
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedCode):
        return CodeBlock(
            id=f"content:{item.id}",
            code=item.code,
            language=item.language,
            normalized_item_ids=(item.id,),
            source_evidence=item.source_evidence,
        )

    if isinstance(item, NormalizedUnknown) and item.text and item.text.strip():
        return TextBlock(
            id=f"content:{item.id}",
            text=item.text.strip(),
            normalized_item_ids=(item.id,),
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
    return clause.heading


def _content_traceability_errors(
    clauses: tuple[Clause, ...],
    normalized: NormalizedExtractedDocument,
) -> tuple[str, ...]:
    active_ids = {item.id for item in normalized.items}
    errors: list[str] = []
    for clause in clauses:
        for block in clause.content:
            if not block.normalized_item_ids:
                errors.append(f"{block.id} has no NormalizedItem reference")
            unknown = set(block.normalized_item_ids) - active_ids
            if unknown:
                errors.append(f"{block.id} references unknown NormalizedItems")
            if not block.source_evidence:
                errors.append(f"{block.id} has no SourceEvidence")
    return tuple(errors)


_TABLE_CAPTION = re.compile(
    r"^Table\s+(?P<reference>(?:[A-Z](?:\.\d+)+|\d+(?:\.\d+)*))"
    r"\s*(?:[—–-]\s*)?(?P<title>.*)$",
    re.IGNORECASE,
)


def _lift_document_tables(
    document: EngineeringDocument,
    clauses: tuple[Clause, ...],
):
    """Attach clause-local TableBlocks to first-class structural table metadata."""
    declared = {table.reference.casefold(): table for table in document.tables}
    tables: list[DocumentTable] = []
    seen: set[str] = set()
    sequence = 0

    for clause in clauses:
        ordinal = 0
        for block in clause.content:
            if not isinstance(block, TableBlock):
                continue
            ordinal += 1
            parsed = _parse_table_caption(block.caption)
            reference = parsed[0] if parsed is not None else f"{clause.reference.clause}.{ordinal}"
            title = parsed[1] if parsed is not None else block.caption
            key = reference.casefold()
            existing = declared.get(key)
            if existing is not None:
                table = existing.model_copy(
                    update={
                        "title": existing.title or title,
                        "parent_clause_id": existing.parent_clause_id or clause.id,
                        "parent_clause_reference": (
                            existing.parent_clause_reference or clause.reference.clause
                        ),
                        "sequence_index": sequence,
                        "table_block_id": block.id,
                        "source_evidence": block.source_evidence,
                    }
                )
            else:
                table = DocumentTable(
                    id=_build_document_table_id(document, reference),
                    reference=reference,
                    title=title,
                    parent_clause_id=clause.id,
                    parent_clause_reference=clause.reference.clause,
                    sequence_index=sequence,
                    table_block_id=block.id,
                    listed_in_table_index=any(
                        entry.reference.casefold() == key for entry in document.table_index
                    ),
                    source_evidence=block.source_evidence,
                )
            tables.append(table)
            seen.add(key)
            sequence += 1

    for existing in document.tables:
        if existing.reference.casefold() not in seen:
            tables.append(existing.model_copy(update={"sequence_index": sequence}))
            sequence += 1

    table_by_reference = {table.reference.casefold(): table for table in tables}
    table_index = tuple(
        entry.model_copy(
            update={
                "table_id": (
                    table_by_reference[entry.reference.casefold()].id
                    if entry.reference.casefold() in table_by_reference
                    else entry.table_id
                )
            }
        )
        for entry in document.table_index
    )
    return tuple(tables), table_index


def _parse_table_caption(caption: str | None) -> tuple[str, str | None] | None:
    if not caption:
        return None
    match = _TABLE_CAPTION.fullmatch(re.sub(r"\s+", " ", caption).strip())
    if match is None:
        return None
    return match.group("reference"), match.group("title").strip() or None


def _build_document_table_id(document: EngineeringDocument, reference: str) -> DocumentTableId:
    raw = f"{document.key.value}|{document.year or ''}|table|{reference.casefold()}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return DocumentTableId(value=f"table-{digest}")
