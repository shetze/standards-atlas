"""Schema/read-path regressions using real repositories and the MCP service boundary."""

import json
from pathlib import Path

import pytest

from standards_atlas import __version__
from standards_atlas.adapters.evaluation import EngineeringDocumentClauseProvider
from standards_atlas.adapters.filesystem import (
    FileSystemEngineeringDocumentRepository,
    FileSystemFormulaTranscriptionRepository,
)
from standards_atlas.adapters.mcp import McpClauseService, McpServerConfig
from standards_atlas.application.schema import (
    SCHEMA_POLICIES,
    SchemaPolicy,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    FormulaBlock,
    SemanticClassification,
    Standard,
    StandardKey,
    StandardReference,
    TextBlock,
)
from standards_atlas.domain.model.knowledge_state import GeneratedAttribute, GenerationMethod

KEY = StandardKey(value="IEC61508-3")
IMAGE = "data:image/png;base64,AAAA"


def _document() -> Standard:
    # Synthetic source content: this fixture does not transcribe an actual IEC formula.
    return Standard(
        key=KEY,
        name="Formula fixture",
        title="Formula fixture",
        clauses=(
            Clause(
                id=ClauseId(value="formula-fixture-1"),
                reference=StandardReference(standard="IEC 61508", part="3", clause="1"),
                clause_type=ClauseType.CLAUSE,
                content=(
                    TextBlock(id="before", text="For the diagnostic interval:"),
                    FormulaBlock(
                        id="content:formula-1",
                        expression="",
                        extraction_status="visual_only",
                        media_type="image/png",
                        content_hash="sha256:abc",
                        embedded_data_uri=IMAGE,
                    ),
                    TextBlock(id="after", text="where T is measured in seconds."),
                ),
            ),
        ),
    )


def _service(workspace: Path, *, enabled=True, allowed=()) -> McpClauseService:
    return McpClauseService(
        EngineeringDocumentClauseProvider(workspace),
        McpServerConfig(
            workspace=workspace,
            allowed_document_keys=allowed,
            capabilities={"formula_transcription": enabled},
        ),
    )


def test_mcp_formula_roundtrip_reads_supported_schema_and_writes_schema1_with_provenance(
    tmp_path: Path,
) -> None:
    documents = FileSystemEngineeringDocumentRepository(tmp_path)
    documents.save(_document())
    path = tmp_path / "documents" / f"{KEY.value}.json"
    payload = json.loads(path.read_text())
    path.write_text(json.dumps(payload))
    before = path.read_bytes()
    service = _service(tmp_path)

    formulas = service.list_untranscribed_formulas(document_keys=[KEY.value], limit=20)
    assert len(formulas) == 1
    formula_id = formulas[0]["formula_id"]
    formula = service.get_formula(formula_id)
    assert formula["image"]["data_uri"] == IMAGE
    assert formula["context"] == {
        "preceding_text": "For the diagnostic interval:",
        "following_text": "where T is measured in seconds.",
    }
    assert path.read_bytes() == before  # Listing/getting must not migrate the file on disk.
    artifact = service.submit_formula_transcription(
        formula_id,
        latex=r"T_D = T_1 + T_2",
        actor="codex",
        provider="openai",
        model="test-model",
        confidence=0.93,
    )

    persisted = FileSystemFormulaTranscriptionRepository(tmp_path).load(formula_id)
    assert persisted.provenance.actor == "codex"
    assert persisted.provenance.provider == "openai"
    assert persisted.provenance.model == "test-model"
    assert persisted.source_content_hash == "sha256:abc"
    assert persisted.model_dump(mode="json") == artifact
    assert json.loads(path.read_text())["schema_version"] == 1
    assert service.list_untranscribed_formulas(document_keys=[KEY.value]) == []
    block = documents.load(KEY).clauses[0].content[1]
    assert isinstance(block, FormulaBlock)
    assert block.expression == r"T_D = T_1 + T_2"
    assert block.extraction_status == "machine_transcribed"
    assert block.representation == "latex"
    assert block.embedded_data_uri == IMAGE


def test_schema1_transcription_preserves_semantic_authority_and_availability(tmp_path) -> None:
    document = _document()
    clause = (
        document.clauses[0]
        .with_semantic_classification(
            SemanticClassification(
                statement_functions=("requirement",), primary_function="requirement"
            )
        )
        .mark_generated(
            GeneratedAttribute(
                path="enrichments.applicability",
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
    documents = FileSystemEngineeringDocumentRepository(tmp_path)
    documents.save(document)
    service = _service(tmp_path)
    formula_id = service.list_untranscribed_formulas(document_keys=[KEY.value])[0]["formula_id"]

    service.submit_formula_transcription(
        formula_id, latex="x = y", actor="codex", model="test-model"
    )

    loaded = documents.load(KEY).clauses[0]
    assert loaded.enrichments == clause.enrichments
    assert loaded.provenance == clause.provenance
    assert loaded.provenance.availability("enrichments.applicability") == "known"
    assert (
        loaded.provenance.availability("enrichments.semantic.role_semantics_present") == "unknown"
    )


def test_scoped_formula_listing_does_not_load_unrelated_obsolete_or_malformed_documents(
    tmp_path,
) -> None:
    documents = FileSystemEngineeringDocumentRepository(tmp_path)
    documents.save(_document())
    root = tmp_path / "documents"
    (root / "A-obsolete.json").write_text('{"schema_version": 7, "document": {}}')
    (root / "Z-malformed.json").write_text("not JSON")
    service = _service(tmp_path)

    formulas = service.list_untranscribed_formulas(document_keys=[KEY.value, KEY.value])

    assert len(formulas) == 1
    assert formulas[0]["document_key"] == KEY.value
    assert service.list_untranscribed_formulas(document_keys=[KEY.value], offset=1) == []
    with pytest.raises(ValueError, match="Unsupported engineering document schema"):
        service.list_untranscribed_formulas()


def test_scoped_formula_listing_still_rejects_selected_unsupported_schema(tmp_path) -> None:
    documents = FileSystemEngineeringDocumentRepository(tmp_path)
    documents.save(_document())
    path = tmp_path / "documents" / f"{KEY.value}.json"
    path.write_text('{"schema_version": 999, "document": {}}')

    with pytest.raises(ValueError, match="Unsupported engineering document schema version: 999"):
        _service(tmp_path).list_untranscribed_formulas(document_keys=[KEY.value])


def test_reproduces_reported_failure_only_with_old_reader_policy(tmp_path, monkeypatch) -> None:
    FileSystemEngineeringDocumentRepository(tmp_path).save(_document())
    service = _service(tmp_path)
    with monkeypatch.context() as old_runtime:
        old_runtime.setitem(
            SCHEMA_POLICIES,
            "engineering-document",
            SchemaPolicy("engineering-document", 9, (9,), ".atlas/data/documents/*.json"),
        )
        with pytest.raises(ValueError) as exc:
            service.list_untranscribed_formulas(document_keys=[KEY.value], limit=20)
        assert str(exc.value) == (
            "Unsupported engineering document schema version: 1; "
            "readable versions are 9, current is 9"
        )

    assert len(service.list_untranscribed_formulas(document_keys=[KEY.value], limit=20)) == 1


def test_formula_tools_preserve_allowlist_and_write_opt_in(tmp_path) -> None:
    documents = FileSystemEngineeringDocumentRepository(tmp_path)
    documents.save(_document())
    service = _service(tmp_path, enabled=False, allowed=(KEY.value,))
    formula_id = service.list_untranscribed_formulas()[0]["formula_id"]

    with pytest.raises(ValueError, match="not exposed"):
        service.list_untranscribed_formulas(document_keys=["hidden"])
    with pytest.raises(ValueError, match="disabled"):
        service.submit_formula_transcription(formula_id, latex="x = y", actor="codex")
    hidden_service = _service(tmp_path, allowed=("another-document",))
    with pytest.raises(KeyError, match="not exposed"):
        hidden_service.submit_formula_transcription(formula_id, latex="x = y", actor="codex")
    assert not FileSystemFormulaTranscriptionRepository(tmp_path).exists(formula_id)
    assert documents.load(KEY) == _document()


def test_runtime_info_is_independent_of_document_readability_and_omits_private_paths(
    tmp_path,
) -> None:
    service = _service(tmp_path, enabled=False)
    (tmp_path / "documents" / "bad.json").write_text("not JSON")

    info = service.get_server_info()

    assert info == {
        "application": {"name": "standards-atlas", "version": __version__},
        "engineering_document_schema": {"current": 1, "readable": [1], "writer": 1},
        "capabilities": {
            "formula_transcription": False,
            "review_read": False,
            "review_preparation": False,
            "review_holdout_assistance": False,
        },
    }
    assert str(tmp_path) not in json.dumps(info)
