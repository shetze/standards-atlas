"""TABLE field migration, HITL updates and captionless alignment roundtrips."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from standards_atlas.adapters.atlasdata.import_pipeline import AtlasDataImportPipeline
from standards_atlas.adapters.atlasdata.parser import TABLE_RECORD_LAYOUT, parse_standard_file
from standards_atlas.adapters.atlasdata.roundtrip_writer import AtlasDataRoundTripWriter
from standards_atlas.adapters.atlasdata.semantic_annotation_writer import (
    AtlasDataSemanticAnnotationService,
)
from standards_atlas.application.alignment import AlignmentEngine
from standards_atlas.application.model import (
    AlignmentStatus,
    NormalizationMetadata,
    NormalizationOptions,
    NormalizationStatistics,
    NormalizedExtractedDocument,
    NormalizedHeading,
    NormalizedTable,
    ReferenceCandidate,
    ReferenceCandidateDocument,
    ReferenceCandidateStatus,
    ReferenceDetectionMetadata,
    ReferenceDetectionStatistics,
    ReferenceMatchKind,
)
from standards_atlas.cli import app
from standards_atlas.domain.model import TableCell, TableRow

LEGACY_SOURCE = """name="Example"
digits=8
oyr=2025
semanticProfile="functional-safety:1.0.0"
structure=(
 "2025 1-7.1 1-b7.1.1 1-9:A.2 1-b9:A.2.0"
)

#---data---#
TOC;heading;Example-1:2025 7.1;Reviewed heading;u;SP-DES,KK-CNC
TOC;annex;Example-1:2025 A.2;Annex heading;u
TABLE;37281310f3247573e93a60a784399e9a;Example-1:2025 Table 1;Reviewed caption;7.1
TABLE;zero;Example-1:2025 Table A.0;;A.2
TABLEINDEX;index;Example-1:2025 Table 1;Listed caption;i
"""


def _table_lines(source: Path) -> list[list[str]]:
    return [
        line.split(";") for line in source.read_text().splitlines() if line.startswith("TABLE;")
    ]


def test_cli_migrates_table_fields_then_preserves_hitl_in_the_last_field(tmp_path):
    source = tmp_path / "EXAMPLE"
    source.write_text(LEGACY_SOURCE, encoding="utf-8")
    importer = AtlasDataImportPipeline()
    before = importer.import_file(source)
    runner = CliRunner()

    preview = runner.invoke(app, ["atlasdata", "generate-toc", str(source)])
    assert preview.exit_code == 0, preview.output
    assert source.read_text() == LEGACY_SOURCE
    assert not source.with_name("EXAMPLE.bak.1").exists()

    written = runner.invoke(app, ["atlasdata", "generate-toc", str(source), "--write"])
    assert written.exit_code == 0, written.output
    assert source.with_name("EXAMPLE.bak.1").read_text() == LEGACY_SOURCE
    assert source.read_text().split("#---data---#")[0] == LEGACY_SOURCE.split("#---data---#")[0]
    assert TABLE_RECORD_LAYOUT in source.read_text()
    assert [row[3:] for row in _table_lines(source)] == [["7.1", "Reviewed caption"], ["A.2", ""]]
    after = importer.import_file(source)
    assert before.tables == after.tables
    assert before.table_index == after.table_index
    assert before.clauses == after.clauses
    assert before.annotations == after.annotations
    hashes = [row[1] for row in _table_lines(source)]

    # A reviewer edits only field 5. A reference-shaped title must remain a title.
    source.write_text(source.read_text().replace(";7.1;Reviewed caption\n", ";7.1;A.2\n"))
    reviewed = importer.import_file(source)
    assert reviewed.tables[0].title == "A.2"
    assert reviewed.tables[0].parent_clause_reference == "7.1"
    repeated = runner.invoke(app, ["atlasdata", "generate-toc", str(source), "--write"])
    assert repeated.exit_code == 0, repeated.output
    assert "Changed               : False" in repeated.output
    assert _table_lines(source)[0][3:] == ["7.1", "A.2"]
    assert [row[1] for row in _table_lines(source)] == hashes
    assert not source.with_name("EXAMPLE.bak.2").exists()


@pytest.mark.parametrize("start_with_new_layout", [False, True])
def test_semantic_annotation_writer_uses_the_same_table_layout(tmp_path, start_with_new_layout):
    source = tmp_path / "EXAMPLE"
    source.write_text(LEGACY_SOURCE, encoding="utf-8")
    importer = AtlasDataImportPipeline()
    before = importer.import_file(source)
    if start_with_new_layout:
        AtlasDataRoundTripWriter().update_toc(source, before, write=True)
    original = source.read_bytes()
    manifest = tmp_path / "annotations.yaml"
    manifest.write_text(
        'schema_version: "2.0"\nsemantic_profile: "functional-safety:1.0.0"\n'
        'annotations:\n  - reference: "Example-1:2025 7.1"\n'
        "    primary_statement_function: requirement\n",
        encoding="utf-8",
    )
    service = AtlasDataSemanticAnnotationService()
    preview = service.apply(source, manifest)
    assert preview.changed
    assert source.read_bytes() == original
    result = service.apply(source, manifest, write=True)
    assert result.backup.read_bytes() == original
    assert [row[3:] for row in _table_lines(source)] == [["7.1", "Reviewed caption"], ["A.2", ""]]
    assert ";Listed caption;i\n" in source.read_text()
    assert ";Reviewed heading;u;SP-REQ\n" in source.read_text()
    after = importer.import_file(source)
    assert after.tables == before.tables
    assert after.table_index == before.table_index
    assert not service.apply(source, manifest, write=True).changed
    # Alternating the two writers must not swap the fields back again.
    AtlasDataRoundTripWriter().update_toc(source, after, write=True)
    assert [row[3:] for row in _table_lines(source)] == [["7.1", "Reviewed caption"], ["A.2", ""]]
    assert not service.apply(source, manifest, write=True).changed


@pytest.mark.parametrize(
    ("structure", "parent", "label"),
    [("1-7.1 1-b7.1.0", "7.1", "0"), ("1-9:A.2 1-b9:A.2.0", "A.2", "A.0")],
)
def test_zero_table_survives_roundtrip_and_captionless_content_stays_aligned(
    tmp_path, structure, parent, label
):
    source = tmp_path / "EXAMPLE"
    source.write_text(
        f'name="Example"\ndigits=8\nstructure=(\n "2025 {structure}"\n)\n',
        encoding="utf-8",
    )
    importer = AtlasDataImportPipeline()
    master = importer.import_file(source)
    before = importer.import_physical(source, document_key="EXAMPLE-1", part="1")
    original_structure = parse_standard_file(source).structure_items
    writer = AtlasDataRoundTripWriter()
    writer.update_toc(source, master, write=True)
    after = importer.import_physical(source, document_key="EXAMPLE-1", part="1")
    assert before.tables == after.tables
    assert len(after.tables) == 1
    table = after.tables[0]
    assert table.reference == label
    assert table.title is None
    assert not table.listed_in_table_index
    assert after.table_index == ()
    assert table.parent_clause_reference == parent
    assert table.parent_clause_id == after.clauses[0].id
    assert _table_lines(source)[0][3:] == [parent, ""]
    assert "TABLEINDEX;" not in source.read_text()
    assert parse_standard_file(source).structure_items == original_structure
    assert not writer.update_toc(source, importer.import_file(source), write=True).changed

    # Run the real alignment engine with a captionless normalized table. The
    # range and structural declaration must be identical after field migration.
    timestamp = datetime(2025, 1, 1, tzinfo=UTC)
    normalized = NormalizedExtractedDocument(
        source_id="EXAMPLE-1",
        items=(
            NormalizedHeading(
                id="heading",
                sequence_number=0,
                source_item_ids=("heading",),
                text=f"{parent} Heading",
            ),
            NormalizedTable(
                id="uncaptioned",
                sequence_number=1,
                source_item_ids=("uncaptioned",),
                caption=None,
                rows=(TableRow(cells=(TableCell(text="Synthetic cell"),)),),
            ),
        ),
        metadata=NormalizationMetadata(
            normalizer_version="test",
            source_extraction_hash="synthetic",
            created_at=timestamp,
            options=NormalizationOptions(),
            statistics=NormalizationStatistics(input_items=2, output_items=2),
        ),
    )
    candidates = ReferenceCandidateDocument(
        source_id="EXAMPLE-1",
        candidates=(
            ReferenceCandidate(
                item_id="heading",
                sequence_number=0,
                raw_reference=parent,
                normalized_reference=parent,
                title_remainder="Heading",
                match_kind=ReferenceMatchKind.EXACT,
                status=ReferenceCandidateStatus.EXPECTED,
                confidence=1.0,
                expected_clause_ids=(after.clauses[0].id.value,),
            ),
        ),
        metadata=ReferenceDetectionMetadata(
            detector_version="test",
            source_normalization_hash="synthetic",
            expected_structure_hash="synthetic",
            created_at=timestamp,
            statistics=ReferenceDetectionStatistics(candidates=1),
        ),
    )
    first = AlignmentEngine().align(normalized, candidates, before)
    second = AlignmentEngine().align(normalized, candidates, after)
    assert first.clauses == second.clauses
    assert second.clauses[0].status == AlignmentStatus.EXACT
    assert second.clauses[0].source_item_ids == ("heading", "uncaptioned")
    assert not second.unassigned_ranges


def test_ambiguous_legacy_fields_fail_before_modifying_the_file(tmp_path):
    source = tmp_path / "EXAMPLE"
    ambiguous = LEGACY_SOURCE.replace(";Reviewed caption;7.1", ";A.2;7.1")
    source.write_text(ambiguous)
    result = CliRunner().invoke(app, ["atlasdata", "generate-toc", str(source), "--write"])
    assert result.exit_code != 0
    assert "Ambiguous TABLE field order" in str(result.exception or result.output)
    assert source.read_text() == ambiguous
    assert not source.with_name("EXAMPLE.bak.1").exists()
