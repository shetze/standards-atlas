from standards_atlas.adapters.atlasdata.domain_mapper import map_atlas_data_to_standard
from standards_atlas.adapters.atlasdata.metadata import AtlasMetadata
from standards_atlas.adapters.atlasdata.parser import AtlasStandardData, InitializationRecord
from standards_atlas.adapters.atlasdata.structure_expander import (
    StructureItem,
)
from standards_atlas.adapters.atlasdata.structure_types import AtlasItemType
from standards_atlas.domain.model import (
    AnnotationType,
    AnnotationVisibility,
    ClauseType,
    DocumentStructure,
)


def test_map_atlas_data_to_standard() -> None:
    atlas_data = AtlasStandardData(
        metadata=AtlasMetadata(
            name="EN 50716",
            digits=8,
            parent="IEC61508",
            official_year=2023,
        ),
        structure_items=[
            StructureItem(
                visible_reference="1",
                item_type=AtlasItemType.TOC,
                source_token="1",
            ),
            StructureItem(
                visible_reference="5.1.1",
                item_type=AtlasItemType.REQUIREMENT,
                source_token="r5.1.{1..2}",
            ),
        ],
        initialization_records=[
            InitializationRecord(
                kind="TOC",
                hash_value="abc",
                reference="EN 50716:2023 1",
                content="Scope",
                type_marker="u",
            ),
            InitializationRecord(
                kind="PublicTXT",
                hash_value="def",
                reference="EN 50716:2023 5.1.1",
                content="Requirement text",
                type_marker="r",
            ),
        ],
    )

    standard = map_atlas_data_to_standard(
        atlas_data,
        key="EN50716",
    )

    assert standard.key.value == "EN50716"
    assert standard.name == "EN 50716"
    assert standard.year == 2023
    assert standard.parent_key is not None
    assert standard.parent_key.value == "IEC61508"

    assert len(standard.clauses) == 2

    scope_clause = standard.clauses[0]

    assert scope_clause.reference.clause == "1"
    assert scope_clause.title == "Scope"
    assert scope_clause.clause_type == ClauseType.TOC

    requirement_clause = standard.clauses[1]

    assert requirement_clause.reference.clause == "5.1.1"
    assert requirement_clause.content == ()
    assert requirement_clause.plain_text == ""
    assert requirement_clause.clause_type == ClauseType.REQUIREMENT

    requirement_annotations = standard.annotations_for_clause(
        requirement_clause.id,
    )

    assert len(requirement_annotations) == 1

    annotation = requirement_annotations[0]

    assert annotation.content == "Requirement text"
    assert annotation.annotation_type == AnnotationType.COMMENT
    assert annotation.visibility == AnnotationVisibility.PUBLIC


def test_clause_ids_are_stable() -> None:
    atlas_data = AtlasStandardData(
        metadata=AtlasMetadata(
            name="Example",
            digits=4,
            official_year=2023,
        ),
        structure_items=[
            StructureItem(
                visible_reference="1",
                item_type=AtlasItemType.TOC,
                source_token="1",
            )
        ],
        initialization_records=[],
    )

    first = map_atlas_data_to_standard(atlas_data, key="EXAMPLE")
    second = map_atlas_data_to_standard(atlas_data, key="EXAMPLE")

    assert first.clauses[0].id == second.clauses[0].id


def test_domain_mapper_infers_document_structure_from_title() -> None:
    atlas_data = AtlasStandardData(
        metadata=AtlasMetadata(
            name="ISO 26262-8",
            digits=8,
            official_year=2018,
        ),
        structure_items=[
            StructureItem(
                visible_reference="5.5",
                item_type=AtlasItemType.TOC,
                source_token="5.5",
            ),
        ],
        initialization_records=[
            InitializationRecord(
                kind="TOC",
                hash_value="abc",
                reference="ISO 26262-8:2018 5.5",
                content="Work products",
                type_marker="u",
            ),
        ],
    )

    standard = map_atlas_data_to_standard(atlas_data, key="ISO26262-8")

    assert (
        standard.clauses[0].semantic_classification.document_structure.category
        is DocumentStructure.BODY
    )


def test_part_zero_titles_are_resolved_per_volume() -> None:
    atlas_data = AtlasStandardData(
        metadata=AtlasMetadata(name="IEC 61508", digits=11, official_year=2010),
        structure_items=[
            StructureItem(
                visible_reference="0",
                item_type=AtlasItemType.TOC,
                volume="1",
                publication_year=2010,
            ),
            StructureItem(
                visible_reference="0",
                item_type=AtlasItemType.TOC,
                volume="2",
                publication_year=2010,
            ),
        ],
        initialization_records=[
            InitializationRecord(
                kind="TOC",
                hash_value="one",
                reference="IEC 61508-1:2010 0",
                content="Part 1",
                type_marker="u",
            ),
            InitializationRecord(
                kind="TOC",
                hash_value="two",
                reference="IEC 61508-2:2010 0",
                content="Part 2",
                type_marker="u",
            ),
        ],
    )

    standard = map_atlas_data_to_standard(atlas_data, key="IEC61508")

    assert [(clause.volume, clause.title) for clause in standard.clauses] == [
        ("1", "Part 1"),
        ("2", "Part 2"),
    ]


def test_domain_mapper_defaults_main_body_to_normative() -> None:
    atlas_data = AtlasStandardData(
        metadata=AtlasMetadata(name="ISO 26262-11", digits=8, official_year=2018),
        structure_items=[
            StructureItem(
                visible_reference="5.3.1",
                item_type=AtlasItemType.CLAUSE,
                source_token="5.3.1",
            )
        ],
        initialization_records=[
            InitializationRecord(
                kind="TOC",
                hash_value="abc",
                reference="ISO 26262-11:2018 5.3.1",
                content="General",
                type_marker="u",
            )
        ],
    )

    standard = map_atlas_data_to_standard(atlas_data, key="ISO26262-11")

    assert standard.clauses[0].semantic_classification.normative_status.value == "normative"


def test_domain_mapper_preserves_informative_annex_status() -> None:
    atlas_data = AtlasStandardData(
        metadata=AtlasMetadata(name="ISO 26262-11", digits=8, official_year=2018),
        structure_items=[
            StructureItem(
                visible_reference="A",
                item_type=AtlasItemType.CLAUSE,
                source_token="A",
            )
        ],
        initialization_records=[
            InitializationRecord(
                kind="TOC",
                hash_value="abc",
                reference="ISO 26262-11:2018 A",
                content="Annex A (informative) — Examples",
                type_marker="u",
            )
        ],
    )

    standard = map_atlas_data_to_standard(atlas_data, key="ISO26262-11")

    assert standard.clauses[0].semantic_classification.normative_status.value == "informative"
