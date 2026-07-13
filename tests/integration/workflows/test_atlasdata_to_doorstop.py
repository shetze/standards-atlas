from __future__ import annotations

from pathlib import Path

import yaml

from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.adapters.doorstop import (
    DoorstopExportConfig,
    DoorstopExporter,
)
from standards_atlas.adapters.filesystem import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.application.services import (
    DocumentExportService,
    DocumentImportService,
)
from standards_atlas.domain.model import DocumentKey

DATA_DIR = Path("data")


def test_atlasdata_to_repository_to_doorstop_round_trip(
    tmp_path: Path,
) -> None:
    source = DATA_DIR / "EN50716"
    workspace = tmp_path / ".atlas"
    doorstop_target = workspace / "doorstop" / "EN50716"

    repository = FileSystemEngineeringDocumentRepository(
        workspace=workspace,
    )

    import_service = DocumentImportService(
        importer=AtlasDataImporter(),
        repository=repository,
    )

    imported_document = import_service.import_document(source)

    assert imported_document.key.value == "EN50716"
    assert imported_document.title == "EN 50716"
    assert len(imported_document.clauses) > 0

    document_key = DocumentKey(value="EN50716")

    assert repository.exists(document_key)

    persisted_document = repository.load(document_key)

    assert persisted_document == imported_document
    assert len(persisted_document.clauses) == len(imported_document.clauses)

    export_service = DocumentExportService(
        exporter=DoorstopExporter(
            config=DoorstopExportConfig(
                workspace=workspace / "doorstop",
                validate_after_export=False,
                initialize_git_repository=False,
            )
        )
    )

    generated_target = export_service.export_document(
        document=persisted_document,
        target=doorstop_target,
    )

    assert generated_target == doorstop_target
    assert doorstop_target.exists()

    config_file = doorstop_target / ".doorstop.yml"

    assert config_file.exists()

    config_data = yaml.safe_load(config_file.read_text(encoding="utf-8"))

    assert config_data["settings"]["prefix"] == "EN50716"
    assert config_data["settings"]["itemformat"] == "yaml"

    item_files = sorted(
        path for path in doorstop_target.glob("*.yml") if path.name != ".doorstop.yml"
    )

    assert len(item_files) == len(persisted_document.clauses)

    first_item = yaml.safe_load(item_files[0].read_text(encoding="utf-8"))

    assert "level" in first_item
    assert "header" in first_item
    assert "text" in first_item
    assert "atlas-clause-id" in first_item
    assert "atlas-reference" in first_item
