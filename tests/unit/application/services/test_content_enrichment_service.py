import hashlib
import json
from datetime import UTC, datetime

import pytest

from standards_atlas.adapters.alignment import AlignmentArtifactRepository
from standards_atlas.adapters.alignment_review import AlignmentReviewRepository
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.normalization import NormalizationArtifactRepository
from standards_atlas.application.model import (
    AlignmentMetadata,
    AlignmentOptions,
    AlignmentResult,
    AlignmentStatistics,
    AlignmentStatus,
    CandidateRemainderKind,
    ClauseAlignment,
    NormalizationMetadata,
    NormalizationOptions,
    NormalizationStatistics,
    NormalizedCode,
    NormalizedExtractedDocument,
    NormalizedFormula,
    NormalizedHeading,
    NormalizedList,
    NormalizedListItem,
    NormalizedTable,
    NormalizedText,
)
from standards_atlas.application.services.content_enrichment_service import ContentEnrichmentError
from standards_atlas.cli.composition import build_content_enrichment_service
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    CodeBlock,
    FormulaBlock,
    ListBlock,
    SourceEvidence,
    Standard,
    StandardKey,
    StandardReference,
    TableBlock,
    TableCell,
    TableRow,
    TextBlock,
)


def test_enriches_clause_ranges_and_removes_structural_heads(tmp_path):
    workspace = tmp_path / ".atlas"
    repository = FileSystemEngineeringDocumentRepository(workspace)
    repository.save(_document())
    evidence = (SourceEvidence(source_id="PDF", source_type="pdf", page_number=3),)
    normalized = _normalized(
        NormalizedHeading(
            id="h1",
            sequence_number=0,
            source_item_ids=("h1",),
            source_evidence=evidence,
            text="1 Scope",
        ),
        NormalizedText(
            id="p1",
            sequence_number=1,
            source_item_ids=("p1",),
            source_evidence=evidence,
            text="First paragraph.",
        ),
        NormalizedList(
            id="l1",
            sequence_number=2,
            source_item_ids=("l1",),
            items=(NormalizedListItem(text="Item"),),
            source_evidence=evidence,
        ),
        NormalizedText(
            id="h2",
            sequence_number=3,
            source_item_ids=("h2",),
            source_evidence=evidence,
            text="2 Inline clause text.",
        ),
        NormalizedTable(
            id="t1",
            sequence_number=4,
            source_item_ids=("t1",),
            rows=(TableRow(cells=(TableCell(text="A"),)),),
            caption="Table 2.1 — Example values",
            source_evidence=evidence,
        ),
        NormalizedCode(
            id="c1",
            sequence_number=5,
            source_item_ids=("c1",),
            source_evidence=evidence,
            code="x = 1",
        ),
    )
    NormalizationArtifactRepository(workspace).save("SAMPLE", normalized)
    AlignmentArtifactRepository(workspace).save(
        "SAMPLE", _alignment(normalized_hash=_model_hash(normalized))
    )

    result = build_content_enrichment_service(workspace).enrich("SAMPLE")
    persisted = repository.load(StandardKey(value="SAMPLE"))

    first, second = persisted.clauses
    assert [type(block) for block in first.content] == [TextBlock, ListBlock]
    assert first.content[0].text == "First paragraph."
    assert first.content[0].source_evidence == evidence
    assert first.title == "Scope"
    assert [type(block) for block in second.content] == [TextBlock, TableBlock, CodeBlock]
    assert second.title == "AtlasData fallback"
    assert second.content[0].text == "Inline clause text."
    assert result.statistics.clauses_enriched == 2
    assert result.statistics.content_blocks == 5
    assert result.statistics.normalized_items_consumed == 6
    assert len(persisted.tables) == 1
    assert persisted.tables[0].reference == "2.1"
    assert persisted.tables[0].title == "Example values"
    assert persisted.tables[0].parent_clause_id == second.id
    assert persisted.tables[0].table_block_id == second.content[1].id


def test_visual_only_formula_discards_docling_pseudo_expression(tmp_path):
    workspace = tmp_path / ".atlas"
    repository = FileSystemEngineeringDocumentRepository(workspace)
    repository.save(_document())
    evidence = (SourceEvidence(source_id="PDF", source_type="pdf", page_number=37),)
    normalized = _normalized(
        NormalizedHeading(
            id="h1",
            sequence_number=0,
            source_item_ids=("h1",),
            source_evidence=evidence,
            text="1 Formula",
        ),
        NormalizedFormula(
            id="f1",
            sequence_number=1,
            source_item_ids=("f1",),
            source_evidence=evidence,
            expression="1 MUT A MUT MDT = <= +",
            original_expression="1 MUT A MUT MDT = <= +",
            extraction_status="visual_only",
        ),
        NormalizedHeading(
            id="h2",
            sequence_number=2,
            source_item_ids=("h2",),
            source_evidence=evidence,
            text="2",
        ),
    )
    NormalizationArtifactRepository(workspace).save("SAMPLE", normalized)
    AlignmentArtifactRepository(workspace).save(
        "SAMPLE",
        _alignment(
            first_end=1, second_start=2, second_end=2, normalized_hash=_model_hash(normalized)
        ),
    )

    build_content_enrichment_service(workspace).enrich("SAMPLE")

    persisted = repository.load(StandardKey(value="SAMPLE"))
    formula = persisted.clauses[0].content[0]
    assert isinstance(formula, FormulaBlock)
    assert formula.extraction_status == "visual_only"
    assert formula.expression == ""
    assert formula.original_expression is None


def test_prefers_reviewed_alignment_when_present(tmp_path):
    workspace = tmp_path / ".atlas"
    FileSystemEngineeringDocumentRepository(workspace).save(_document())
    evidence = (SourceEvidence(source_id="PDF", source_type="pdf", page_number=1),)
    normalized = _normalized(
        NormalizedHeading(
            id="h1", sequence_number=0, source_item_ids=("h1",), source_evidence=evidence, text="1"
        ),
        NormalizedText(
            id="p1",
            sequence_number=1,
            source_item_ids=("p1",),
            source_evidence=evidence,
            text="Body",
        ),
        NormalizedHeading(
            id="h2", sequence_number=2, source_item_ids=("h2",), source_evidence=evidence, text="2"
        ),
    )
    NormalizationArtifactRepository(workspace).save("SAMPLE", normalized)
    automatic = _alignment(
        first_end=1,
        second_start=2,
        second_end=2,
        normalized_hash=_model_hash(normalized),
    )
    reviewed_second = automatic.clauses[1].model_copy(update={"status": AlignmentStatus.MANUAL})
    reviewed = automatic.model_copy(update={"clauses": automatic.clauses[:1] + (reviewed_second,)})
    AlignmentArtifactRepository(workspace).save("SAMPLE", automatic)
    review_repository = AlignmentReviewRepository(tmp_path / "local" / "review" / "alignment")
    review_repository.save_reviewed(
        "SAMPLE",
        reviewed,
        automatic_alignment_hash=review_repository.hash_alignment(automatic),
    )

    result = build_content_enrichment_service(workspace).enrich("SAMPLE")

    assert result.statistics.used_reviewed_alignment is True
    assert result.statistics.construction_contract.valid is True


def test_rejects_unresolved_alignment_by_default(tmp_path):
    workspace = tmp_path / ".atlas"
    FileSystemEngineeringDocumentRepository(workspace).save(_document())
    normalized = _normalized()
    NormalizationArtifactRepository(workspace).save("SAMPLE", normalized)
    complete = _alignment(normalized_hash=_model_hash(normalized))
    missing = complete.clauses[0].model_copy(
        update={
            "status": AlignmentStatus.MISSING,
            "start_sequence_number": None,
            "end_sequence_number": None,
        }
    )
    alignment = complete.model_copy(update={"clauses": (missing, complete.clauses[1])})
    AlignmentArtifactRepository(workspace).save("SAMPLE", alignment)

    with pytest.raises(ContentEnrichmentError, match="unresolved clauses"):
        build_content_enrichment_service(workspace).enrich("SAMPLE")


def _document():
    return Standard(
        key=StandardKey(value="SAMPLE"),
        title="Sample",
        name="Sample",
        clauses=tuple(
            Clause(
                id=ClauseId(value=f"SAMPLE-{number}"),
                reference=StandardReference(standard="SAMPLE", clause=number),
                clause_type=ClauseType.CLAUSE,
                title="AtlasData fallback" if number == "2" else None,
            )
            for number in ("1", "2")
        ),
    )


def _normalized(*items):
    return NormalizedExtractedDocument(
        source_id="SAMPLE",
        items=items,
        metadata=NormalizationMetadata(
            normalizer_version="test",
            source_extraction_hash="hash",
            created_at=datetime.now(UTC),
            options=NormalizationOptions(),
            statistics=NormalizationStatistics(input_items=len(items), output_items=len(items)),
        ),
    )


def _alignment(
    second_start=3,
    second_end=5,
    *,
    first_end=2,
    normalized_hash="n",
):
    clauses = (
        ClauseAlignment(
            clause_id="SAMPLE-1",
            expected_reference="1",
            candidate_item_id="h1",
            status=AlignmentStatus.EXACT,
            start_sequence_number=0,
            end_sequence_number=first_end,
            remainder_kind=CandidateRemainderKind.TITLE,
            observed_remainder="Scope",
        ),
        ClauseAlignment(
            clause_id="SAMPLE-2",
            expected_reference="2",
            candidate_item_id="h2",
            status=AlignmentStatus.EXACT,
            start_sequence_number=second_start,
            end_sequence_number=second_end,
            remainder_kind=CandidateRemainderKind.CONTENT,
            observed_remainder="Inline clause text.",
        ),
    )
    return AlignmentResult(
        source_id="SAMPLE",
        clauses=clauses,
        metadata=AlignmentMetadata(
            alignment_version="test",
            normalized_document_hash=normalized_hash,
            candidate_document_hash="c",
            expected_structure_hash="s",
            created_at=datetime.now(UTC),
            options=AlignmentOptions(),
            statistics=AlignmentStatistics(expected_clauses=2, exact_matches=2),
        ),
    )


def _model_hash(model) -> str:
    payload = model.model_dump(mode="json")
    payload.get("metadata", {}).pop("created_at", None)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
