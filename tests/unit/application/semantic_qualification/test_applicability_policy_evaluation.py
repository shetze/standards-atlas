from __future__ import annotations

from datetime import UTC, datetime

from standards_atlas.application.semantic_qualification.applicability_corpus import (
    ApplicabilityGoldenCase,
    ApplicabilityGoldenCorpus,
    ApplicabilityGoldenExpected,
    ApplicabilityGoldenProvenance,
)
from standards_atlas.application.semantic_qualification.applicability_policy_evaluation import (
    evaluate_applicability_policy,
)
from standards_atlas.application.semantic_qualification.applicability_policy_replay import (
    ApplicabilityPolicyReplayCase,
    ApplicabilityPolicyReplayReport,
    ApplicabilityPolicyRoleSource,
)

NOW = datetime(2026, 9, 8, tzinfo=UTC)
SHA = "a" * 64


def _golden(index: int, *, present: bool) -> ApplicabilityGoldenCase:
    return ApplicabilityGoldenCase(
        clause_id=f"clause-{index}",
        document_key="ISO26262-X",
        reference=f"ISO26262-X:{index}",
        text=f"Clause {index}",
        category="policy",
        status="published",
        expected=ApplicabilityGoldenExpected(present=present),
        provenance=ApplicabilityGoldenProvenance(
            source_archive="qualification-run-073.zip",
            source_archive_sha256=SHA,
        ),
    )


def _role(role: str, prompt: str, task: str) -> ApplicabilityPolicyRoleSource:
    return ApplicabilityPolicyRoleSource(
        role=role,  # type: ignore[arg-type]
        path=f"{role}.json",
        sha256=SHA,
        task_version=task,
        prompt_version=prompt,
        model_id="mistral",
        model_ref="mistral/model",
        selected_clause_count=3,
    )


def _replay(final_values: tuple[bool | None, ...]) -> ApplicabilityPolicyReplayReport:
    cases = []
    for index, final in enumerate(final_values, start=1):
        selected = index <= 3
        gate = selected
        cases.append(
            ApplicabilityPolicyReplayCase(
                document_key="ISO26262-X",
                clause_id=f"clause-{index}",
                reference=f"ISO26262-X:{index}",
                gate_present=gate,
                detail_selected=selected,
                primary_present=final if selected else None,
                rescue_present=False if selected else None,
                confirmation_present=False if selected else None,
                detail_present=final if selected else None,
                final_present=final if selected else False,
            )
        )
    return ApplicabilityPolicyReplayReport(
        generated_at=NOW,
        source_run="qualification-run-073.zip",
        source_run_sha256=SHA,
        source_matrix_id="matrix-v6",
        source_corpus_id="semantic-profile-v1",
        source_selection_sha256=SHA,
        consensus_clause_count=len(cases),
        selected_clause_count=3,
        final_positive_count=sum(case.final_present is True for case in cases),
        final_negative_count=sum(case.final_present is False for case in cases),
        final_unknown_count=sum(case.final_present is None for case in cases),
        roles=(
            _role("primary", "detail-structure-aware-v4", "2.0.0"),
            _role("rescue", "detail-structure-aware-v3", "2.0.0"),
            _role("confirmation", "detail-structure-aware-v1", "1.0.0"),
        ),
        cases=tuple(cases),
    )


def test_error_budget_passes_at_two_fp_and_two_fn() -> None:
    golden = ApplicabilityGoldenCorpus(
        cases=tuple(
            _golden(index, present=expected)
            for index, expected in enumerate((False, False, True, True), start=1)
        )
    )
    replay = _replay((True, True, False, False))

    report = evaluate_applicability_policy(golden, replay)

    assert report.metrics.false_positive == 2
    assert report.metrics.false_negative == 2
    assert report.passed is True


def test_unknown_golden_decision_fails_even_within_error_budget() -> None:
    golden = ApplicabilityGoldenCorpus(cases=(_golden(1, present=True),))
    replay = _replay((None, False, False, False))

    report = evaluate_applicability_policy(golden, replay)

    assert report.unknown_cases == ("ISO26262-X/clause-1",)
    assert report.passed is False
