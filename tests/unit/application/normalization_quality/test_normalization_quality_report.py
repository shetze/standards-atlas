from pathlib import Path

from standards_atlas.application.normalization_quality import (
    FindingType,
    NormalizationQualityCase,
    NormalizationQualityFinding,
    NormalizationQualityReporter,
    NormalizationQualityRun,
    QualityStatus,
    Severity,
)


def _case(example_id, model_id, status, findings=()):
    return NormalizationQualityCase(
        example_id=example_id,
        document_key="ISO26262-6",
        reference=example_id,
        title=None,
        text="Clause text",
        status=status,
        findings=findings,
        model_id=model_id,
        model_ref=model_id,
        provider="fake",
        duration_ms=10,
        cached=False,
        input_hash="i",
        raw_response_hash="r",
    )


def test_report_highlights_model_disagreements_and_writes_findings_jsonl(tmp_path: Path) -> None:
    finding = NormalizationQualityFinding(
        type=FindingType.BLOCK_MERGE_ERROR,
        severity=Severity.MEDIUM,
        evidence="a.b",
        explanation="Possible merged blocks.",
        confidence=0.9,
    )
    mistral = NormalizationQualityRun(
        "dataset.json",
        "v1",
        "mistral",
        "mistral-ref",
        "fake",
        (_case("7.4.3", "mistral", QualityStatus.SUSPICIOUS, (finding,)),),
    )
    gemma = NormalizationQualityRun(
        "dataset.json",
        "v1",
        "gemma",
        "gemma-ref",
        "fake",
        (_case("7.4.3", "gemma", QualityStatus.OK),),
    )

    json_path, jsonl_path, markdown_path = NormalizationQualityReporter().write(
        (mistral, gemma), tmp_path
    )

    assert json_path.is_file()
    assert len(jsonl_path.read_text(encoding="utf-8").splitlines()) == 1
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Model disagreements: 1" in markdown
    assert "block_merge_error" in markdown
    assert "observational" in markdown
