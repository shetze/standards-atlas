from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.cli.composition import build_document_selection_service
from standards_atlas.domain.model import (
    AnnotationId,
    Clause,
    ClauseAnnotation,
    ClauseId,
    ClauseType,
    Standard,
    StandardKey,
    StandardReference,
)


def test_derives_part_scoped_standard_and_related_annotations(tmp_path):
    workspace = tmp_path / ".atlas"
    part7 = Clause(
        id=ClauseId(value="part-7"),
        reference=StandardReference(standard="ISO 26262", clause="1", part="7"),
        clause_type=ClauseType.CLAUSE,
    )
    part8 = Clause(
        id=ClauseId(value="part-8"),
        reference=StandardReference(standard="ISO 26262", clause="1", part="8"),
        clause_type=ClauseType.CLAUSE,
    )
    repository = FileSystemEngineeringDocumentRepository(workspace)
    repository.save(
        Standard(
            key=StandardKey(value="ISO26262"),
            title="ISO 26262",
            name="ISO 26262",
            clauses=(part7, part8),
            annotations=(
                ClauseAnnotation(
                    id=AnnotationId(value="a7"),
                    clause_id=part7.id,
                    annotation_type="title",
                    visibility="public",
                    content="Part 7",
                ),
                ClauseAnnotation(
                    id=AnnotationId(value="a8"),
                    clause_id=part8.id,
                    annotation_type="title",
                    visibility="public",
                    content="Part 8",
                ),
            ),
        )
    )

    derived = build_document_selection_service(workspace).derive_by_volume(
        "ISO26262", "ISO26262-8", "8", "ISO 26262-8"
    )

    assert derived.key.value == "ISO26262-8"
    assert derived.parent_key.value == "ISO26262"
    assert [clause.id.value for clause in derived.clauses] == ["part-8"]
    assert [annotation.id.value for annotation in derived.annotations] == ["a8"]
    assert repository.load(StandardKey(value="ISO26262-8")) == derived


def test_derive_by_volume_preserves_clause_zero_part_root(tmp_path):
    workspace = tmp_path / ".atlas"
    anchor = Clause(
        id=ClauseId(value="part-8-anchor"),
        reference=StandardReference(standard="ISO 26262", clause="0", part="8"),
        clause_type=ClauseType.CLAUSE,
    )
    clause = Clause(
        id=ClauseId(value="part-8-clause"),
        reference=StandardReference(standard="ISO 26262", clause="1", part="8"),
        clause_type=ClauseType.CLAUSE,
    )
    repository = FileSystemEngineeringDocumentRepository(workspace)
    repository.save(
        Standard(
            key=StandardKey(value="ISO26262"),
            title="ISO 26262",
            name="ISO 26262",
            clauses=(anchor, clause),
        )
    )

    derived = build_document_selection_service(workspace).derive_by_volume(
        "ISO26262", "ISO26262-8", "8", "ISO 26262-8"
    )

    assert [item.reference.clause for item in derived.clauses] == ["0", "1"]
    assert derived.clauses[0].heading == "Part 8"
