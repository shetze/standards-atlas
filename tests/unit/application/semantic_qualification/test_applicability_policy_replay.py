from __future__ import annotations

from datetime import UTC, datetime

import pytest

from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailClauseResult,
    ApplicabilityDetailFailure,
    ApplicabilityDetailGenerator,
    ApplicabilityDetailOutcome,
)
from standards_atlas.application.semantic_qualification.applicability_policy_replay import (
    normalize_detail_presence,
)
from standards_atlas.domain.model import ApplicabilityTarget

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def _generator(*, task_version: str, prompt_version: str) -> ApplicabilityDetailGenerator:
    return ApplicabilityDetailGenerator(
        model_id="mistral-small",
        model="mistral/model",
        provider="openai-compatible",
        task_version=task_version,
        prompt_version=prompt_version,
        input_hash="input",
        raw_response_hash="response",
        duration_ms=1,
        generated_at=NOW,
    )


def _common() -> dict[str, object]:
    return {
        "example_id": "example-1",
        "document_key": "IEC61508-3",
        "clause_id": "clause-1",
        "content_hash": f"sha256:{'a' * 64}",
        "presence_confidence": 1.0,
    }


def test_task_v1_presence_is_projected_from_target() -> None:
    result = ApplicabilityDetailClauseResult(
        **_common(),
        outcome=ApplicabilityDetailOutcome.UNRESOLVED,
        applicability_target=ApplicabilityTarget.CLAUSE_OR_REQUIREMENT,
        evidence_grounded=False,
        generator=_generator(task_version="1.0.0", prompt_version="detail-structure-aware-v1"),
    )

    assert normalize_detail_presence(result) is True


def test_task_v2_unresolved_preserves_positive_presence() -> None:
    result = ApplicabilityDetailClauseResult(
        **_common(),
        outcome=ApplicabilityDetailOutcome.UNRESOLVED,
        applicability_target=ApplicabilityTarget.CLAUSE_OR_REQUIREMENT,
        contains_clause_or_requirement_applicability=True,
        evidence_grounded=False,
        generator=_generator(task_version="2.0.0", prompt_version="detail-structure-aware-v4"),
    )

    assert normalize_detail_presence(result) is True


def test_failed_result_is_unknown() -> None:
    result = ApplicabilityDetailClauseResult(
        **_common(),
        outcome=ApplicabilityDetailOutcome.FAILED,
        failure=ApplicabilityDetailFailure(
            error_type="LlmResponseError",
            message="truncated",
            category="invalid_response",
            finish_reason="length",
        ),
    )

    assert normalize_detail_presence(result) is None


def test_task_v2_missing_presence_is_rejected() -> None:
    result = ApplicabilityDetailClauseResult(
        **_common(),
        outcome=ApplicabilityDetailOutcome.NOT_CONFIRMED,
        applicability_target=ApplicabilityTarget.METHOD_OR_TECHNIQUE,
        evidence_grounded=True,
        generator=_generator(task_version="2.0.0", prompt_version="detail-structure-aware-v4"),
    )

    with pytest.raises(ValueError, match="missing clause applicability Presence"):
        normalize_detail_presence(result)
