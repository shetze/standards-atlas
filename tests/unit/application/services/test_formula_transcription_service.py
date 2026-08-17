from pathlib import Path

from standards_atlas.adapters.filesystem import (
    FileSystemEngineeringDocumentRepository,
    FileSystemFormulaTranscriptionRepository,
)
from standards_atlas.application.services.formula_transcription_service import (
    FormulaTranscriptionService,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    FormulaBlock,
    Standard,
    StandardKey,
    StandardReference,
    TextBlock,
)


def _service(tmp_path: Path) -> FormulaTranscriptionService:
    documents = FileSystemEngineeringDocumentRepository(tmp_path)
    documents.save(
        Standard(
            key=StandardKey(value="EXAMPLE"),
            title="Example",
            name="Example",
            clauses=(
                Clause(
                    id=ClauseId(value="example-1"),
                    reference=StandardReference(standard="Example", clause="1"),
                    clause_type=ClauseType.CLAUSE,
                    content=(
                        TextBlock(id="before", text="For the diagnostic interval:"),
                        FormulaBlock(
                            id="content:formula-1",
                            expression="",
                            extraction_status="visual_only",
                            media_type="image/png",
                            content_hash="sha256:abc",
                            embedded_data_uri="data:image/png;base64,AAAA",
                        ),
                        TextBlock(id="after", text="where T is measured in seconds."),
                    ),
                ),
            ),
        )
    )
    return FormulaTranscriptionService(
        documents,
        FileSystemFormulaTranscriptionRepository(tmp_path),
    )


def test_lists_and_reads_visual_only_formula_with_context(tmp_path: Path) -> None:
    service = _service(tmp_path)

    formulas = service.list_untranscribed()
    assert len(formulas) == 1
    formula_id = formulas[0]["formula_id"]
    formula = service.get(formula_id)

    assert formula["image"]["media_type"] == "image/png"
    assert formula["context"] == {
        "preceding_text": "For the diagnostic interval:",
        "following_text": "where T is measured in seconds.",
    }


def test_submission_persists_artifact_and_updates_formula_block(tmp_path: Path) -> None:
    service = _service(tmp_path)
    formula_id = service.list_untranscribed()[0]["formula_id"]

    artifact = service.submit(
        formula_id,
        latex=r"T_D = T_1 + T_2",
        actor="codex",
        provider="openai",
        model="gpt-test",
        confidence=0.93,
    )

    assert artifact["representation"] == "latex"
    assert artifact["source_content_hash"] == "sha256:abc"
    assert service.list_untranscribed() == []

    document = service._documents.load(StandardKey(value="EXAMPLE"))
    block = document.clauses[0].content[1]
    assert isinstance(block, FormulaBlock)
    assert block.expression == r"T_D = T_1 + T_2"
    assert block.representation == "latex"
    assert block.extraction_status == "machine_transcribed"
