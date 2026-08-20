from pathlib import Path

import pytest

from standards_atlas.adapters.atlasdata.domain_mapper import parse_standard_domain_file
from standards_atlas.adapters.atlasdata.parser import parse_standard_file

DATA_DIR = Path("data")


def _discover_standard_files(data_dir: Path) -> list[Path]:
    """Return extensionless AtlasData source files from the data directory.

    Generated and auxiliary artifacts may live beside the source files.  AtlasData
    standard sources currently use extensionless file names, so use that positive
    format contract instead of trying to maintain an exclusion list.
    """
    return sorted(
        path
        for path in data_dir.iterdir()
        if path.is_file() and path.suffix == "" and not path.name.startswith("mapping")
    )


STANDARD_FILES = _discover_standard_files(DATA_DIR)


def test_standard_file_discovery_ignores_non_atlas_artifacts(tmp_path: Path) -> None:
    (tmp_path / "ISO26262").write_text("name=ISO26262\ndigits=2\n", encoding="utf-8")
    (tmp_path / "mapping01").write_text("auxiliary", encoding="utf-8")
    (tmp_path / "heatmap01.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "Clauses.tlpx").write_text("archive", encoding="utf-8")
    (tmp_path / "relations.csv").write_text("a,b", encoding="utf-8")

    assert _discover_standard_files(tmp_path) == [tmp_path / "ISO26262"]


@pytest.mark.parametrize("data_file", STANDARD_FILES, ids=lambda path: path.name)
def test_expanded_structure_matches_existing_atlas_items(data_file: Path) -> None:
    atlas_data = parse_standard_file(data_file)
    standard = parse_standard_domain_file(data_file)

    expanded_clause_references = {clause.reference.clause for clause in standard.clauses}

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

    remainder = reference[len(standard_name) :].strip()
    parts = remainder.split(maxsplit=1)

    if len(parts) != 2:
        return None

    return parts[1].strip()
