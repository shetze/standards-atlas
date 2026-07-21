from pathlib import Path

import pytest

from standards_atlas.adapters.atlasdata.parser import parse_standard_file
from standards_atlas.adapters.atlasdata.structure_types import AtlasItemType


@pytest.mark.parametrize("filename", ["IEC61508", "ISO26262", "EN50716"])
def test_representative_legacy_atlasdata_files_parse(filename: str) -> None:
    atlas_data = parse_standard_file(Path("data") / filename)

    assert atlas_data.structure_items


def test_iec61508_canonical_typed_annex_tokens_keep_type_and_enum_prefix() -> None:
    atlas_data = parse_standard_file(Path("data/IEC61508"))
    clause = next(
        item
        for item in atlas_data.structure_items
        if item.volume == "2" and item.visible_reference == "C.1"
    )

    assert clause.item_type == AtlasItemType.REQUIREMENT
    assert clause.enum_prefix == "11"
    assert clause.source_token == "2-r11:C.{1..2}"


def test_transitional_typed_annex_tokens_remain_readable(tmp_path: Path) -> None:
    source = tmp_path / "TRANSITIONAL"
    source.write_text(
        'name="Transitional"\ndigits=8\n\nstructure=(\n "2026 11:rC.1"\n)\n',
        encoding="utf-8",
    )

    atlas_data = parse_standard_file(source)
    clause = atlas_data.structure_items[0]

    assert clause.visible_reference == "C.1"
    assert clause.item_type == AtlasItemType.REQUIREMENT
    assert clause.enum_prefix == "11"
