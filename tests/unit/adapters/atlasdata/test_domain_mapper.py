from standards_atlas.adapters.atlasdata.domain_mapper import map_atlas_data_to_standard
from standards_atlas.adapters.atlasdata.metadata import AtlasMetadata
from standards_atlas.adapters.atlasdata.parser import AtlasStandardData, InitializationRecord
from standards_atlas.adapters.atlasdata.structure_types import AtlasItemType
from standards_atlas.adapters.atlasdata.structure_expander import (
    StructureItem,
)
from standards_atlas.domain.model import ClauseType


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
                kind="TEXT",
                hash_value="def",
                reference="EN 50716:2023 5.1.1",
                content="Requirement text",
                type_marker="s",
            ),
        ],
    )

    standard = map_atlas_data_to_standard(atlas_data, key="EN50716")

    assert standard.key.value == "EN50716"
    assert standard.name == "EN 50716"
    assert standard.year == 2023
    assert standard.parent_key is not None
    assert standard.parent_key.value == "IEC61508"

    assert len(standard.clauses) == 2

    assert standard.clauses[0].reference.clause == "1"
    assert standard.clauses[0].title == "Scope"
    assert standard.clauses[0].clause_type == ClauseType.TOC

    assert standard.clauses[1].reference.clause == "5.1.1"
    assert standard.clauses[1].text == "Requirement text"
    assert standard.clauses[1].clause_type == ClauseType.REQUIREMENT


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
