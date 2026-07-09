from pathlib import Path

from standards_atlas.adapters.atlasdata.import_pipeline import AtlasDataImportPipeline
from standards_atlas.domain.model import EngineeringDocument


def test_atlas_data_import_pipeline_imports_file_as_engineering_document() -> None:
    pipeline = AtlasDataImportPipeline()

    document = pipeline.import_file(Path("data/EN50716"))

    assert isinstance(document, EngineeringDocument)
    assert document.title
    assert len(document.clauses) > 0


def test_atlas_data_import_pipeline_uses_explicit_key() -> None:
    pipeline = AtlasDataImportPipeline()

    document = pipeline.import_file(Path("data/EN50716"), key="CUSTOM-KEY")

    assert document.key.value == "CUSTOM-KEY"
