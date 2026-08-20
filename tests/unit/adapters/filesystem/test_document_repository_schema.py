import json
from pathlib import Path

import pytest

from standards_atlas.adapters.filesystem.document_repository import (
    CURRENT_DOCUMENT_SCHEMA_VERSION,
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.domain.model import (
    CanonicalDocumentSection,
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    StructuralProfile,
    TextBlock,
)


def _document() -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="DOC"),
        title="Example Document",
        document_type=DocumentType.OTHER,
        clauses=(
            Clause(
                id=ClauseId(value="DOC-1"),
                reference=StandardReference(
                    standard="Example",
                    year=2026,
                    clause="1",
                ),
                clause_type=ClauseType.CLAUSE,
                structural_profile=StructuralProfile(
                    canonical_section=CanonicalDocumentSection.BODY
                ),
                content=(TextBlock(id="DOC-1-text", text="Protected content."),),
            ),
        ),
    )


def test_repository_writes_versioned_document_envelope(tmp_path: Path) -> None:
    workspace = tmp_path / ".atlas"
    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)

    repository.save(_document())

    payload = json.loads((workspace / "documents" / "DOC.json").read_text())
    assert payload["schema_version"] == CURRENT_DOCUMENT_SCHEMA_VERSION
    assert payload["document"]["clauses"][0]["content"][0]["type"] == "text"
    assert "text" not in payload["document"]["clauses"][0]
    assert payload["document"]["clauses"][0]["structural_profile"]["canonical_section"] == "body"
    loaded = repository.load(DocumentKey(value="DOC"))
    assert loaded.clauses[0].structural_profile is not None
    assert loaded.clauses[0].structural_profile.canonical_section is CanonicalDocumentSection.BODY


def test_repository_rejects_unversioned_legacy_document(tmp_path: Path) -> None:
    workspace = tmp_path / ".atlas"
    documents = workspace / "documents"
    documents.mkdir(parents=True)
    legacy = {
        "key": {"value": "DOC"},
        "title": "Legacy Document",
        "document_type": "other",
        "clauses": [],
    }
    (documents / "DOC.json").write_text(json.dumps(legacy), encoding="utf-8")

    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)
    with pytest.raises(ValueError, match="missing 'schema_version'"):
        repository.load(DocumentKey(value="DOC"))


def test_repository_rejects_unknown_schema_version(tmp_path: Path) -> None:
    workspace = tmp_path / ".atlas"
    documents = workspace / "documents"
    documents.mkdir(parents=True)
    payload = {"schema_version": 999, "document": {}}
    (documents / "DOC.json").write_text(json.dumps(payload), encoding="utf-8")

    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)

    with pytest.raises(ValueError, match="Unsupported engineering document schema version"):
        repository.load(DocumentKey(value="DOC"))
