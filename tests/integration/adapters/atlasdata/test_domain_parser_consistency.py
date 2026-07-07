from pathlib import Path

import pytest

from standards_atlas.adapters.atlasdata.domain_mapper import parse_standard_domain_file
from standards_atlas.adapters.atlasdata.parser import parse_standard_file


DATA_DIR = Path("data")


STANDARD_FILES = [
    path
    for path in DATA_DIR.iterdir()
    if path.is_file()
    and not path.name.startswith("mapping")
    and not path.name.endswith(".tlpx")
    and path.name != "relations.csv"
]


@pytest.mark.parametrize("data_file", STANDARD_FILES, ids=lambda path: path.name)
def test_expanded_structure_matches_existing_atlas_items(data_file: Path) -> None:
    atlas_data = parse_standard_file(data_file)
    standard = parse_standard_domain_file(data_file)

    expanded_clause_references = {
        clause.reference.clause
        for clause in standard.clauses
    }

    atlas_item_references = {
        ref
        for ref in (
            _extract_clause_reference(record.reference, standard.name)
            for record in atlas_data.initialization_records
            if record.kind == "TOC"
        )
        if ref is not None
    }

    assert expanded_clause_references == atlas_item_references


def _extract_clause_reference(reference: str, standard_name: str) -> str | None:
    if not reference.startswith(standard_name):
        return None

    remainder = reference[len(standard_name):].strip()
    parts = remainder.split(maxsplit=1)

    if len(parts) != 2:
        return None

    return parts[1].strip()
