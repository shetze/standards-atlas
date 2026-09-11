"""Synthetic regression coverage for table numbering, migration and content binding."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from standards_atlas.adapters.alignment import AlignmentArtifactRepository
from standards_atlas.adapters.atlasdata.import_pipeline import AtlasDataImportPipeline
from standards_atlas.adapters.atlasdata.parser import parse_initialization_records
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
    NormalizedExtractedDocument,
    NormalizedHeading,
    NormalizedTable,
)
from standards_atlas.application.services.table_normalization_service import (
    TableNormalizationService,
)
from standards_atlas.cli import app
from standards_atlas.cli.composition import build_content_enrichment_service
from standards_atlas.domain.model import SourceEvidence, TableBlock, TableCell, TableRow

LEGACY_SOURCE = """name="Example"
digits=8
oyr=2025
semanticProfile="functional-safety:1.0.0"
structure=(
 "2024 1-0 1-r7.1 1-b7.1.1 1-8.2.18 1-b8.2.18.5"
 "2025 2-0 2-7.1 2-b7.1.1 2-9:A 2-9:A.2 2-b9:A.2.14 2-9:A.3 2-b9:A.3.15"
)

#---data---#
TOC;heading;Example-1:2024 7.1;Reviewed heading;r;SP-DES,KK-CNC
TABLE;old1;Example-1:2024 Table 7.1.1;First part caption;7.1
TABLE;old5;Example-1:2024 Table 8.2.18.5;Fifth table caption;8.2.18
TABLE;old2;Example-2:2025 Table 7.1.1;Second part caption;7.1
TABLE;old14;Example-2:2025 Table A.2.14;Annex caption fourteen;A.2
TABLE;old15;Example-2:2025 Table A.3.15;Annex caption fifteen;A.3
TABLE;new2;Example-2:2025 Table 1;Reviewed second part caption;7.1
TABLE;orphan;Example:2025 Table Z.1;Unassigned explicit table;
TABLEINDEX;index2;Example-2:2025 Table 7.1.1;Old list caption;i
TABLEINDEX;newindex2;Example-2:2025 Table 1;Reviewed list caption;i
TABLEINDEX;index15;Example-2:2025 Table A.3.15;Annex list caption;i
TABLEINDEX;index99;Example:2025 Table 99;Unlinked list entry;i
"""


def test_generate_toc_migrates_existing_records_and_is_idempotent(tmp_path: Path):
    source = tmp_path / "EXAMPLE"
    source.write_text(LEGACY_SOURCE, encoding="utf-8")
    importer = AtlasDataImportPipeline()
    original_document = importer.import_file(source)
    runner = CliRunner()

    dry_run = runner.invoke(app, ["atlasdata", "generate-toc", str(source)])
    assert dry_run.exit_code == 0, dry_run.output
    assert source.read_text(encoding="utf-8") == LEGACY_SOURCE
    assert not source.with_name("EXAMPLE.bak.1").exists()

    written = runner.invoke(app, ["atlasdata", "generate-toc", str(source), "--write"])
    assert written.exit_code == 0, written.output
    updated = source.read_text(encoding="utf-8")
    assert source.with_name("EXAMPLE.bak.1").read_text(encoding="utf-8") == LEGACY_SOURCE
    assert updated.split("#---data---#")[0] == LEGACY_SOURCE.split("#---data---#")[0]
    records = parse_initialization_records(updated)
    tables = [record for record in records if record.kind == "TABLE"]
    assert [(record.reference, record.type_marker) for record in tables] == [
        ("Example-1:2024 Table 1", "7.1"),
        ("Example-1:2024 Table 5", "8.2.18"),
        ("Example-2:2025 Table 1", "7.1"),
        ("Example-2:2025 Table A.14", "A.2"),
        ("Example-2:2025 Table A.15", "A.3"),
        ("Example:2025 Table Z.1", ""),
    ]
    assert tables[2].content == "Reviewed second part caption"
    assert tables[4].content == "Annex caption fifteen"
    index = [record for record in records if record.kind == "TABLEINDEX"]
    assert [(record.reference, record.content) for record in index] == [
        ("Example-2:2025 Table 1", "Reviewed list caption"),
        ("Example-2:2025 Table A.15", "Annex list caption"),
        ("Example:2025 Table 99", "Unlinked list entry"),
    ]
    heading = next(record for record in records if record.reference == "Example-1:2024 7.1")
    assert heading.content == "Reviewed heading"
    assert heading.semantic_tags == ("SP-DES", "KK-CNC")
    for record in tables + index:
        namespace = record.kind.lower()
        assert (
            record.hash_value == hashlib.md5(f"{namespace}|{record.reference}".encode()).hexdigest()
        )
    migrated = importer.import_file(source)
    assert [clause.id for clause in migrated.clauses] == [
        clause.id for clause in original_document.clauses
    ]
    assert migrated.tables == original_document.tables
    assert migrated.table_index == original_document.table_index

    repeated = runner.invoke(app, ["atlasdata", "generate-toc", str(source), "--write"])
    assert repeated.exit_code == 0, repeated.output
    assert "Changed               : False" in repeated.output
    assert source.read_text(encoding="utf-8") == updated
    assert not source.with_name("EXAMPLE.bak.2").exists()


def test_physical_part_import_filters_tables_and_index_by_identity(tmp_path: Path):
    source = tmp_path / "EXAMPLE"
    source.write_text(LEGACY_SOURCE, encoding="utf-8")
    importer = AtlasDataImportPipeline()
    master = importer.import_file(source)
    first = importer.import_physical(source, document_key="EXAMPLE-1", part="1")
    second = importer.import_physical(source, document_key="EXAMPLE-2", part="2")

    assert [table.reference for table in first.tables] == ["1", "5"]
    assert [table.reference for table in second.tables] == ["1", "A.14", "A.15"]
    assert first.tables[0].id != second.tables[0].id
    assert first.table_index == ()
    assert [entry.reference for entry in second.table_index] == ["1", "A.15"]
    for document in (first, second):
        assert all(
            table.parent_clause_id in {c.id for c in document.clauses} for table in document.tables
        )
        assert all(
            entry.table_id in {t.id for t in document.tables} for entry in document.table_index
        )
    assert len(master.tables) == 6  # Unassigned explicit records remain in the master.
    assert len(master.table_index) == 3


@pytest.mark.parametrize(("part", "parent"), [("1", "7.1"), ("2", "8.2")])
def test_caption_binding_reuses_the_correct_part_table_without_duplicates(tmp_path, part, parent):
    source = tmp_path / "EXAMPLE"
    source.write_text(
        'name="Example"\ndigits=8\nstructure=(\n "2025 1-7.1 1-b7.1.1 2-8.2 2-b8.2.1"\n)\n',
        encoding="utf-8",
    )
    key = f"EXAMPLE-{part}"
    document = AtlasDataImportPipeline().import_physical(source, document_key=key, part=part)
    clause = document.clauses[0]
    declared = next(table for table in document.tables if table.parent_clause_id == clause.id)
    workspace = tmp_path / ".atlas"
    repository = FileSystemEngineeringDocumentRepository(workspace)
    repository.save(document)
    evidence = (SourceEvidence(source_id=key, source_type="pdf", page_number=1),)
    normalized = NormalizedExtractedDocument(
        source_id=key,
        items=(
            NormalizedHeading(
                id="heading",
                sequence_number=0,
                source_item_ids=("heading",),
                source_evidence=evidence,
                text=f"{parent} Heading",
            ),
            NormalizedTable(
                id="table",
                sequence_number=1,
                source_item_ids=("table",),
                source_evidence=evidence,
                caption="Table 1 — Synthetic caption",
                rows=(TableRow(cells=(TableCell(text="Private synthetic cell"),)),),
            ),
        ),
        metadata=NormalizationMetadata(
            normalizer_version="test",
            source_extraction_hash="synthetic",
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
            options=NormalizationOptions(),
            statistics=NormalizationStatistics(input_items=2, output_items=2),
        ),
    )
    payload = normalized.model_dump(mode="json")
    payload["metadata"].pop("created_at", None)
    normalized_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    alignment = AlignmentResult(
        source_id=key,
        clauses=(
            ClauseAlignment(
                clause_id=clause.id.value,
                expected_reference=parent,
                candidate_item_id="heading",
                status=AlignmentStatus.EXACT,
                start_sequence_number=0,
                end_sequence_number=1,
                remainder_kind=CandidateRemainderKind.TITLE,
                observed_remainder="Heading",
            ),
        ),
        metadata=AlignmentMetadata(
            alignment_version="test",
            normalized_document_hash=normalized_hash,
            candidate_document_hash="synthetic",
            expected_structure_hash="synthetic",
            created_at=datetime(2025, 1, 1, tzinfo=UTC),
            options=AlignmentOptions(),
            statistics=AlignmentStatistics(expected_clauses=1, exact_matches=1),
        ),
    )
    NormalizationArtifactRepository(workspace).save(key, normalized)
    AlignmentArtifactRepository(workspace).save(key, alignment)

    enriched = build_content_enrichment_service(workspace).enrich(key).document

    assert len(enriched.tables) == 1
    table = enriched.tables[0]
    assert table.id == declared.id
    assert table.reference == "1"
    assert table.parent_clause_id == clause.id
    assert table.parent_clause_reference == parent
    assert table.title == "Synthetic caption"
    assert isinstance(enriched.clauses[0].content[0], TableBlock)
    assert table.table_block_id == enriched.clauses[0].content[0].id
    normalized_tables = TableNormalizationService().normalize_document(enriched)
    assert len(normalized_tables) == 1
    assert normalized_tables[0].document_table_id == declared.id
    assert normalized_tables[0].reference == "1"
