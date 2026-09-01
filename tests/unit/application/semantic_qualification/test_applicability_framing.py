from datetime import UTC, datetime
from pathlib import Path

import yaml

from standards_atlas.application.semantic_qualification.annotations import (
    AnnotationGenerator,
    AnnotationLifecycleStatus,
    ClauseEvaluationAnnotation,
    ClauseReference,
    StatementFunctionSelection,
    normalized_content_hash,
)
from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCase,
    ApplicabilityGoldenCorpus,
    ApplicabilityGoldenExpected,
    ApplicabilityGoldenProvenance,
)
from standards_atlas.application.semantic_qualification.applicability_framing import (
    build_applicability_framing_report,
    persist_applicability_framing_report,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    MatrixObservation,
    ModelCandidate,
    PromptCandidate,
    QualificationMatrixManifest,
)
from standards_atlas.domain.model import ApplicabilityFunction


def _reference(clause_id: str) -> ClauseReference:
    text = f"Clause {clause_id}"
    return ClauseReference(
        knowledge_domain="functional-safety",
        document_key="IEC61508-3",
        clause_id=clause_id,
        content_hash=normalized_content_hash(text),
    )


def _prediction(
    reference: ClauseReference,
    *,
    present: bool,
    subtype: ApplicabilityFunction | None = None,
) -> ClauseEvaluationAnnotation:
    functions = (subtype,) if subtype is not None else ()
    return ClauseEvaluationAnnotation(
        task="semantic-profile-classification",
        lifecycle_status=AnnotationLifecycleStatus.PROPOSED,
        clause=reference,
        proposal=StatementFunctionSelection(
            applicability_present=present,
            applicability_functions=functions,
            primary_applicability_function=subtype,
            confidence=0.8,
        ),
        generator=AnnotationGenerator(
            provider="local",
            model="model-a",
            prompt_id="prompt",
            generated_at=datetime(2026, 8, 31, tzinfo=UTC),
        ),
    )


def _write(run: Path, annotation: ClauseEvaluationAnnotation) -> None:
    path = run / annotation.clause.document_key / annotation.clause.clause_id / "evaluation.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {"annotation_candidate": annotation.model_dump(mode="json", exclude_none=True)},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _manifest(tmp_path: Path, full: Path, minimal: Path) -> QualificationMatrixManifest:
    return QualificationMatrixManifest(
        matrix_id="applicability-framing-test",
        corpus_id="semantic-profile-v1",
        prompts=(
            PromptCandidate(
                id="applicability-clean-full",
                prompt_version="structure-aware-v8",
                cbox_frame="full-context-v1",
            ),
            PromptCandidate(
                id="applicability-clean-minimal",
                prompt_version="structure-aware-v8",
                cbox_frame="applicability-minimal-v1",
            ),
            PromptCandidate(
                id="applicability-clean-isolated",
                prompt_version="structure-aware-v8",
                cbox_frame="applicability-isolated-v1",
            ),
            PromptCandidate(
                id="content-only",
                prompt_version="content-only-v6",
            ),
        ),
        models=(ModelCandidate(id="model-a", provider="local"),),
        observations=(
            MatrixObservation(
                prompt_id="applicability-clean-full",
                model_id="model-a",
                repetition=1,
                qualification_report=tmp_path / "q1.json",
                run_directory=full,
            ),
            MatrixObservation(
                prompt_id="applicability-clean-minimal",
                model_id="model-a",
                repetition=1,
                qualification_report=tmp_path / "q2.json",
                run_directory=minimal,
            ),
        ),
    )


def test_framing_report_measures_presence_deltas_and_golden_errors(tmp_path: Path) -> None:
    c1 = _reference("c1")
    c2 = _reference("c2")
    full = tmp_path / "full"
    minimal = tmp_path / "minimal"
    _write(full, _prediction(c1, present=True, subtype=ApplicabilityFunction.INCLUSION))
    _write(full, _prediction(c2, present=True, subtype=ApplicabilityFunction.INCLUSION))
    _write(minimal, _prediction(c1, present=False))
    _write(minimal, _prediction(c2, present=True, subtype=ApplicabilityFunction.EXCLUSION))

    provenance = ApplicabilityGoldenProvenance(
        source_archive="test.zip", source_archive_sha256="0" * 64
    )
    golden = ApplicabilityGoldenCorpus(
        cases=(
            ApplicabilityGoldenCase(
                clause_id="c1",
                document_key="IEC61508-3",
                reference="IEC61508-3 c1",
                text="Clause c1",
                category="minority_presence_disagreement",
                status="published",
                expected=ApplicabilityGoldenExpected(present=False),
                provenance=provenance,
            ),
            ApplicabilityGoldenCase(
                clause_id="c2",
                document_key="IEC61508-3",
                reference="IEC61508-3 c2",
                text="Clause c2",
                category="polarity_disagreement",
                status="published",
                expected=ApplicabilityGoldenExpected(
                    present=True,
                    polarity="excluded",
                ),
                provenance=provenance,
            ),
        ),
    )
    golden_path = tmp_path / "golden.yaml"
    golden_path.write_text(
        yaml.safe_dump(golden.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )

    report = build_applicability_framing_report(
        manifest=_manifest(tmp_path, full, minimal), golden_path=golden_path
    )

    assert report.schema_version == "2.0"
    assert len(report.observations) == 2
    baseline = next(row for row in report.observations if row.cbox_frame == "full-context-v1")
    candidate = next(
        row for row in report.observations if row.cbox_frame == "applicability-minimal-v1"
    )
    assert baseline.false_positives == 1
    assert candidate.false_positives == 0
    assert candidate.false_negatives == 0
    assert candidate.polarity_accuracy == 1.0

    delta = report.comparisons[0]
    assert delta.presence_disagreement_count == 1
    assert delta.polarity_disagreement_count == 1
    assert delta.changed_to_absent == 1
    assert delta.golden_outcome == "improved"
    assert (delta.baseline_golden_errors, delta.candidate_golden_errors) == (1, 0)

    json_path, markdown_path = persist_applicability_framing_report(report, tmp_path / "out")
    assert json_path.exists()
    rendered = markdown_path.read_text(encoding="utf-8")
    assert "Full-context deltas" in rendered
    assert "Polarity Δ" in rendered
    assert "Subtype Δ" not in rendered
    assert "improved" in rendered


def test_framing_report_is_descriptive_without_golden_corpus(tmp_path: Path) -> None:
    reference = _reference("c1")
    full = tmp_path / "full"
    minimal = tmp_path / "minimal"
    _write(full, _prediction(reference, present=True, subtype=ApplicabilityFunction.INCLUSION))
    _write(minimal, _prediction(reference, present=False))

    report = build_applicability_framing_report(
        manifest=_manifest(tmp_path, full, minimal),
        golden_path=tmp_path / "missing.yaml",
    )

    assert report.comparisons[0].golden_outcome == "unscored"
    assert report.comparisons[0].baseline_golden_errors is None
    assert any("descriptive only" in item for item in report.diagnostics)
