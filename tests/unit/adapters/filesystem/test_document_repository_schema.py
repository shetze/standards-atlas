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
    SemanticClassification,
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
                    part="3",
                ),
                clause_type=ClauseType.CLAUSE,
                heading="Scope",
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
    assert payload["document"]["clauses"][0]["baseline"]["content"][0]["type"] == "text"
    assert "text" not in payload["document"]["clauses"][0]
    assert (
        payload["document"]["clauses"][0]["baseline"]["structural_profile"]["canonical_section"]
        == "body"
    )
    clause_payload = payload["document"]["clauses"][0]
    assert clause_payload["baseline"]["heading"] == "Scope"
    assert clause_payload["reference"]["part"] == "3"
    assert "title" not in clause_payload
    assert "volume" not in clause_payload
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


def test_repository_rejects_obsolete_schema_version(tmp_path: Path) -> None:
    workspace = tmp_path / ".atlas"
    documents = workspace / "documents"
    documents.mkdir(parents=True)
    payload = {
        "schema_version": CURRENT_DOCUMENT_SCHEMA_VERSION - 2,
        "document": _document().model_dump(mode="json"),
    }
    (documents / "DOC.json").write_text(json.dumps(payload), encoding="utf-8")

    repository = FileSystemEngineeringDocumentRepository(workspace=workspace)
    with pytest.raises(ValueError, match="Unsupported engineering document schema version"):
        repository.load(DocumentKey(value="DOC"))


def test_v8_nondefault_unmarked_values_are_preserved_without_invented_authority(
    tmp_path: Path,
) -> None:
    document = _document()
    clause = document.clauses[0].with_semantic_classification(
        SemanticClassification(
            applicability_present=True,
        )
    )
    document = document.model_copy(update={"clauses": (clause,)})
    path = tmp_path / "documents" / "DOC.json"
    path.parent.mkdir()
    payload = {"schema_version": 8, "document": document.model_dump(mode="json")}
    # Reproduce the older payload; no v9 authority or availability fields existed.
    payload["document"]["clauses"][0]["provenance"] = {"generated_attributes": []}
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    from standards_atlas.application.schema.policy import SchemaDeprecationWarning

    with pytest.warns(SchemaDeprecationWarning):
        loaded = FileSystemEngineeringDocumentRepository(tmp_path).load(document.key)
    assert path.read_bytes() == before
    provenance = loaded.clauses[0].provenance
    assert provenance.protection("enrichments.semantic.applicability_present") == "unattributed"
    assert provenance.confirmed_attributes == ()
    assert provenance.availability("enrichments.semantic.role_semantics_present") == "not_evaluated"


def test_v9_roundtrip_preserves_known_false_unknown_and_primary(tmp_path: Path) -> None:
    from standards_atlas.domain.model.knowledge_state import GeneratedAttribute, GenerationMethod

    document = _document()
    clause = (
        document.clauses[0]
        .with_semantic_classification(
            SemanticClassification(
                statement_functions=("requirement",),
                primary_function="requirement",
            )
        )
        .mark_generated(
            GeneratedAttribute(
                path="enrichments.semantic.applicability_present",
                generator="test",
                method=GenerationMethod.IMPORTED,
            ),
            GeneratedAttribute(
                path="enrichments.semantic.role_semantics_present",
                generator="test",
                method=GenerationMethod.IMPORTED,
                availability="unknown",
            ),
        )
        .confirm_authoritative(
            "enrichments.semantic.statement_functions",
            "enrichments.semantic.primary_function",
            authority="review",
        )
    )
    document = document.model_copy(update={"clauses": (clause,)})
    repository = FileSystemEngineeringDocumentRepository(tmp_path)
    repository.save(document)
    loaded = repository.load(document.key)
    assert loaded == document
    provenance = loaded.clauses[0].provenance
    assert provenance.availability("enrichments.semantic.applicability_present") == "known"
    assert provenance.availability("enrichments.semantic.role_semantics_present") == "unknown"
    assert provenance.availability("enrichments.semantic.process_functions") == "not_evaluated"
