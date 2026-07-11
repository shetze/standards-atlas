from standards_atlas.adapters.atlasdata.parser import (
    AtlasStandardData,
    AtlasMetadata,
    InitializationRecord,
    StructureItem,
)
from standards_atlas.adapters.atlasdata.structure_types import AtlasItemType
from standards_atlas.domain.model.annotation import (
    AnnotationType,
    AnnotationVisibility,
    ClauseAnnotation,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
)
from standards_atlas.adapters.atlasdata.domain_mapper import map_atlas_data_to_standard


def test_atlasdata_records_are_imported_as_public_annotations() -> None:
    atlas_data = AtlasStandardData(
        metadata=AtlasMetadata(
            name="Example",
            digits=4,
            official_year=2025,
        ),
        structure_items=[
            StructureItem(
                visible_reference="1",
                item_type=AtlasItemType.TOC,
                source_token="1",
                publication_year=2025,
            ),
        ],
        initialization_records=[
            InitializationRecord(
                kind="TOC",
                hash_value="toc-hash",
                reference="Example:2025 1",
                content="Public heading",
                type_marker="u",
            ),
            InitializationRecord(
                kind="PublicTXT",
                hash_value="text-hash",
                reference="Example:2025 1",
                content="Public summary",
                type_marker="u",
            ),
        ],
    )

    document = map_atlas_data_to_standard(
        atlas_data,
        key="EXAMPLE",
    )

    assert {
        annotation.visibility
        for annotation in document.annotations
    } == {
        AnnotationVisibility.PUBLIC,
    }

    assert {
        annotation.annotation_type
        for annotation in document.annotations
    } == {
        AnnotationType.TITLE,
        AnnotationType.COMMENT,
    }
