import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from standards_atlas.adapters.filesystem import (
    FileSystemComposedDocumentViewRepository,
    FileSystemEngineeringDocumentRepository,
    FileSystemPublicationDocumentReader,
)
from standards_atlas.application.model import ComposedDocumentView
from standards_atlas.domain.model import DocumentKey, DocumentType, EngineeringDocument


def _document(key: str) -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value=key),
        title=key,
        document_type=DocumentType.OTHER,
    )


def test_publication_reader_prefers_work_view_without_canonical_family_file(
    tmp_path: Path,
) -> None:
    documents = FileSystemEngineeringDocumentRepository(tmp_path / "data")
    documents.save(_document("PART-1"))
    views = FileSystemComposedDocumentViewRepository(tmp_path / "work")
    views.save(
        ComposedDocumentView(
            family_key="FAMILY",
            part_keys=("PART-1",),
            document=_document("FAMILY"),
        )
    )

    payload = json.loads((tmp_path / "work" / "composed-documents" / "FAMILY.json").read_text())
    assert payload["schema_version"] == 2

    reader = FileSystemPublicationDocumentReader(documents, views)

    assert reader.load(DocumentKey(value="FAMILY")).key.value == "FAMILY"
    assert [document.key.value for document in reader.list()] == ["PART-1"]
    assert not documents.exists(DocumentKey(value="FAMILY"))


def test_publication_reader_skips_unreadable_stale_documents_for_cross_references(
    tmp_path: Path,
) -> None:
    documents = FileSystemEngineeringDocumentRepository(tmp_path / "data")
    documents.save(_document("CURRENT"))
    stale_path = tmp_path / "data" / "documents" / "STALE.json"
    stale_path.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "document": _document("STALE").model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    views = FileSystemComposedDocumentViewRepository(tmp_path / "work")
    reader = FileSystemPublicationDocumentReader(documents, views)

    assert [document.key.value for document in reader.list()] == ["CURRENT"]


def test_publication_reader_does_not_hide_invalid_current_documents(
    tmp_path: Path,
) -> None:
    documents = FileSystemEngineeringDocumentRepository(tmp_path / "data")
    invalid_path = tmp_path / "data" / "documents" / "BROKEN.json"
    invalid_path.write_text(
        json.dumps(
            {
                "schema_version": 6,
                "document": {
                    "key": {"value": "BROKEN"},
                    "document_type": "other",
                },
            }
        ),
        encoding="utf-8",
    )
    views = FileSystemComposedDocumentViewRepository(tmp_path / "work")
    reader = FileSystemPublicationDocumentReader(documents, views)

    with pytest.raises(ValidationError):
        reader.list()
