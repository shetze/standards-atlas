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
    NormalizedHeading,
    NormalizedList,
    NormalizedListItem,
    NormalizedTable,
    NormalizedText,
)
from standards_atlas.application.services import (
    ContentEnrichmentError,
    ContentEnrichmentService,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    CodeBlock,
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
    NormalizationArtifactRepository(workspace).save(
        "SAMPLE",
        _normalized(
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
            ),
            NormalizedText(
                id="h2", sequence_number=3, source_item_ids=("h2",), text="2 Inline clause text."
            ),
            NormalizedTable(
                id="t1",
                sequence_number=4,
                source_item_ids=("t1",),
                rows=(TableRow(cells=(TableCell(text="A"),)),),
            ),
            NormalizedCode(id="c1", sequence_number=5, source_item_ids=("c1",), code="x = 1"),
        ),
    )
    AlignmentArtifactRepository(workspace).save("SAMPLE", _alignment())

    result = ContentEnrichmentService(workspace).enrich("SAMPLE")
    persisted = repository.load(StandardKey(value="SAMPLE"))

    first, second = persisted.clauses
    assert [type(block) for block in first.content] == [TextBlock, ListBlock]
    assert first.content[0].text == "First paragraph."
    assert first.content[0].source_evidence == evidence
    assert [type(block) for block in second.content] == [TextBlock, TableBlock, CodeBlock]
    assert second.content[0].text == "Inline clause text."
    assert result.statistics.clauses_enriched == 2
    assert result.statistics.content_blocks == 5
    assert result.statistics.normalized_items_consumed == 6


def test_prefers_reviewed_alignment_when_present(tmp_path):
    workspace = tmp_path / ".atlas"
    FileSystemEngineeringDocumentRepository(workspace).save(_document())
    NormalizationArtifactRepository(workspace).save(
        "SAMPLE",
        _normalized(
            NormalizedHeading(id="h1", sequence_number=0, source_item_ids=("h1",), text="1"),
            NormalizedText(id="p1", sequence_number=1, source_item_ids=("p1",), text="Body"),
            NormalizedHeading(id="h2", sequence_number=2, source_item_ids=("h2",), text="2"),
        ),
    )
    automatic = _alignment(second_start=2, second_end=2)
    reviewed_second = automatic.clauses[1].model_copy(update={"status": AlignmentStatus.MANUAL})
    reviewed = automatic.model_copy(update={"clauses": automatic.clauses[:1] + (reviewed_second,)})
    AlignmentArtifactRepository(workspace).save("SAMPLE", automatic)
    AlignmentReviewRepository(workspace).save_reviewed("SAMPLE", reviewed)

    result = ContentEnrichmentService(workspace).enrich("SAMPLE")

    assert result.statistics.used_reviewed_alignment is True


def test_rejects_unresolved_alignment_by_default(tmp_path):
    workspace = tmp_path / ".atlas"
    FileSystemEngineeringDocumentRepository(workspace).save(_document())
    NormalizationArtifactRepository(workspace).save("SAMPLE", _normalized())
    complete = _alignment()
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
        ContentEnrichmentService(workspace).enrich("SAMPLE")


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


def _alignment(second_start=3, second_end=5):
    clauses = (
        ClauseAlignment(
            clause_id="SAMPLE-1",
            expected_reference="1",
            candidate_item_id="h1",
            status=AlignmentStatus.EXACT,
            start_sequence_number=0,
            end_sequence_number=2,
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
            normalized_document_hash="n",
            candidate_document_hash="c",
            expected_structure_hash="s",
            created_at=datetime.now(UTC),
            options=AlignmentOptions(),
            statistics=AlignmentStatistics(expected_clauses=2, exact_matches=2),
        ),
    )
