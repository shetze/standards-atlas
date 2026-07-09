from pathlib import Path

from standards_atlas.adapters.atlasdata import AtlasDataImporter
from standards_atlas.application.services import (
    DocumentImportService,
)


def test_import_en50716() -> None:

    service = DocumentImportService(
        AtlasDataImporter(),
    )

    document = service.import_document(
        Path("data/EN50716"),
    )

    assert document.title == "EN 50716"
    assert len(document.clauses) > 0
