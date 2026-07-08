from pathlib import Path

from standards_atlas.adapters.atlasdata.atlas_importer import AtlasDataImporter
from standards_atlas.domain.model import EngineeringDocument


def test_atlas_data_importer_imports_file_as_engineering_document() -> None:
    importer = AtlasDataImporter()

    document = importer.import_file(Path("data/EN50716"))

    assert isinstance(document, EngineeringDocument)
    assert document.title
    assert len(document.clauses) > 0


def test_atlas_data_importer_uses_explicit_key() -> None:
    importer = AtlasDataImporter()

    document = importer.import_file(Path("data/EN50716"), key="CUSTOM-KEY")

    assert document.key.value == "CUSTOM-KEY"
