from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.evaluation.repository import PromptRepository
from standards_atlas.application.ports.llm_gateway import (
    LlmHealth,
    LlmUnavailableError,
    StructuredGenerationResult,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailEnrichmentConfig,
    ApplicabilityDetailEnrichmentService,
    ApplicabilityDetailOutcome,
    build_applicability_detail_selection,
    parse_applicability_detail_prediction_v2,
    validate_reused_applicability_detail_selection,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
    OverallConsensusStatus,
)
from standards_atlas.application.semantic_qualification.proposals import SemanticTaskRepository
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    build_qualification_coverage,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
    QualificationSelectionClause,
)

RESOURCES = Path("src/standards_atlas/resources/semantic")


class SequenceGateway:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.requests = []

    def health(self) -> LlmHealth:
        return LlmHealth(True, ("model-ref",))

    def generate_structured(self, request):
        self.calls += 1
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return StructuredGenerationResult(
            value=response,
            model=request.model or "model-ref",
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash=f"input-{self.calls}",
            raw_response_hash=f"response-{self.calls}",
            duration_ms=10,
            cached=False,
            raw_response={"value": response},
        )


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _example(index: int, text: str) -> EvaluationExample:
    return EvaluationExample(
        id=f"example-{index}",
        input={
            "content": {"text": text, "hash": _hash(text)},
            "context": {
                "document_key": "DOC",
                "clause_id": f"clause-{index}",
                "reference": f"{index}",
                "title": f"Clause {index}",
            },
        },
        expected={},
    )


def _selection(count: int) -> QualificationRunSelection:
    clauses = tuple(
        QualificationSelectionClause(
            example_id=f"example-{index}",
            document_key="DOC",
            clause_id=f"clause-{index}",
        )
        for index in range(1, count + 1)
    )
    return QualificationRunSelection(
        task="semantic-profile-classification",
        dataset_version="2.2.0",
        corpus_id="semantic-profile-v1",
        dataset_sha256="a" * 64,
        corpus_sha256="b" * 64,
        dataset_clause_count=count,
        corpus_clause_count=count,
        selected_clause_count=count,
        clauses=clauses,
    )


def _consensus(*presence: bool) -> ConsensusReport:
    clauses = tuple(
        ClauseConsensus(
            clause_id=f"clause-{index}",
            document_key="DOC",
            reference=f"{index}",
            heading=f"Clause {index}",
            category=ConsensusCategory.UNANIMOUS,
            applicability_category=ConsensusCategory.UNANIMOUS,
            overall_status=OverallConsensusStatus.RESOLVED,
            applicability_present=value,
            confidence=1.0,
            applicability_confidence=1.0,
            applicability_presence_confidence=1.0,
            applicability_decision_confidence=1.0,
            participating_models=3,
            applicability_participating_models=3,
            requires_review=False,
            resolution_sources={"applicability": "final-escalation"},
        )
        for index, value in enumerate(presence, start=1)
    )
    return ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="semantic-profile-v1",
        prompt_id="applicability-presence",
        reasoning_mode_id="disabled",
        generated_at=datetime.now(UTC),
        model_count=3,
        clause_count=len(clauses),
        categories={"unanimous": len(clauses)},
        review_count=0,
        clauses=clauses,
    )


def _detail_selection(
    *,
    examples: tuple[EvaluationExample, ...],
    consensus: ConsensusReport,
    run_selection: QualificationRunSelection | None = None,
):
    persisted_selection = run_selection or _selection(len(examples))
    return build_applicability_detail_selection(
        run_selection=persisted_selection,
        examples=examples,
        consensus=consensus,
        coverage=build_qualification_coverage(
            selection=persisted_selection,
            report=consensus,
        ),
        task_version="1.0.0",
    )


def _service(gateway: SequenceGateway, artifact_root: Path | None = None):
    task, schema = SemanticTaskRepository(RESOURCES / "tasks").load(
        "applicability-detail-enrichment", "1.0.0"
    )
    assert task.applicability_taxonomy
    assert task.applicability_target_taxonomy == (
        "clause_or_requirement",
        "method_or_technique",
        "process_or_activity",
        "object_or_component",
        "other",
        "none",
    )
    prompt = PromptRepository(RESOURCES / "prompts").load(
        "applicability-detail-enrichment", "detail-structure-aware-v1"
    )
    config = ApplicabilityDetailEnrichmentConfig(
        enabled=True,
        model="detail-model",
        retry_attempts=1,
        retry_backoff_seconds=0,
    )
    return ApplicabilityDetailEnrichmentService(
        gateway,
        config=config,
        prompt=prompt,
        canonical_schema=schema,
        model_id="detail-model",
        model_ref="model-ref",
        artifact_root=artifact_root,
    )


def _service_v2(gateway: SequenceGateway, artifact_root: Path | None = None):
    task, schema = SemanticTaskRepository(RESOURCES / "tasks").load(
        "applicability-detail-enrichment", "2.0.0"
    )
    assert task.other_applicability_target_taxonomy == (
        "method_or_technique",
        "process_or_activity",
        "object_or_component",
        "other",
    )
    prompt = PromptRepository(RESOURCES / "prompts").load(
        "applicability-detail-enrichment", "detail-structure-aware-v2"
    )
    config = ApplicabilityDetailEnrichmentConfig(
        enabled=True,
        task_version="2.0.0",
        prompt_version="detail-structure-aware-v2",
        model="detail-model",
        retry_attempts=1,
        retry_backoff_seconds=0,
    )
    return ApplicabilityDetailEnrichmentService(
        gateway,
        config=config,
        prompt=prompt,
        canonical_schema=schema,
        model_id="detail-model",
        model_ref="model-ref",
        artifact_root=artifact_root,
    )


def test_selection_contains_only_final_presence_positive_clauses() -> None:
    examples = (
        _example(1, "This clause applies to onboard equipment."),
        _example(2, "The supplier records the result."),
        _example(3, "These requirements apply to the referenced subsystem."),
    )

    selected = _detail_selection(
        examples=examples,
        consensus=_consensus(True, False, True),
    )

    assert selected.selected_clause_count == 2
    assert selected.source_selected_clause_count == 3
    assert selected.source_qualified_clause_count == 3
    assert selected.source_unqualified_clause_count == 0
    assert selected.source_consensus_clause_count == 3
    assert [item.clause_id for item in selected.clauses] == ["clause-1", "clause-3"]
    assert all(item.presence_resolution_source == "final-escalation" for item in selected.clauses)


def test_selection_rejects_missing_consensus_for_qualified_clause() -> None:
    examples = (
        _example(1, "This clause applies to onboard equipment."),
        _example(2, "The supplier records the result."),
    )
    run_selection = _selection(2)
    complete_consensus = _consensus(True, False)
    coverage = build_qualification_coverage(
        selection=run_selection,
        report=complete_consensus,
    )
    incomplete_consensus = complete_consensus.model_copy(
        update={
            "clause_count": 1,
            "clauses": complete_consensus.clauses[:1],
        }
    )

    with pytest.raises(
        ValueError,
        match="final consensus coordinates differ from qualified coverage: missing=1",
    ):
        build_applicability_detail_selection(
            run_selection=run_selection,
            examples=examples,
            consensus=incomplete_consensus,
            coverage=coverage,
            task_version="1.0.0",
        )


def test_selection_accepts_clause_explicitly_marked_unqualified() -> None:
    examples = (
        _example(1, "This clause applies to onboard equipment."),
        _example(2, "The supplier records the result."),
    )
    run_selection = _selection(2)
    consensus = _consensus(True).model_copy(update={"clause_count": 1})
    coverage = build_qualification_coverage(selection=run_selection, report=consensus)

    selected = build_applicability_detail_selection(
        run_selection=run_selection,
        examples=examples,
        consensus=consensus,
        coverage=coverage,
        task_version="1.0.0",
    )

    assert selected.selected_clause_count == 1
    assert selected.source_consensus_clause_count == 1
    assert selected.source_qualified_clause_count == 1
    assert selected.source_unqualified_clause_count == 1


def test_sparse_enrichment_classifies_grounded_unresolved_and_empty_details(
    tmp_path: Path,
) -> None:
    texts = (
        "These requirements apply to new systems.",
        "Applicability is described in the referenced clause.",
        "The clause applies to legacy systems.",
    )
    examples = tuple(_example(index, text) for index, text in enumerate(texts, start=1))
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True, True, True),
    )
    gateway = SequenceGateway(
        {
            "applicability_target": "clause_or_requirement",
            "applicability_functions": ["inclusion"],
            "evidence": [
                {"function": "inclusion", "text": "apply to new systems"},
            ],
        },
        {
            "applicability_target": "none",
            "applicability_functions": [],
            "evidence": [],
        },
        {
            "applicability_target": "clause_or_requirement",
            "applicability_functions": ["inclusion"],
            "evidence": [
                {"function": "inclusion", "text": "apply to future systems"},
            ],
        },
    )

    report = _service(gateway, tmp_path / "artifacts").enrich(
        selection=selection,
        examples=examples,
    )

    assert gateway.calls == 3
    assert [item.outcome for item in report.clauses] == [
        ApplicabilityDetailOutcome.ENRICHED,
        ApplicabilityDetailOutcome.NOT_CONFIRMED,
        ApplicabilityDetailOutcome.UNRESOLVED,
    ]
    assert report.enriched_clause_count == 1
    assert report.not_confirmed_clause_count == 1
    assert report.unresolved_clause_count == 1
    assert report.failed_clause_count == 0
    assert (tmp_path / "artifacts" / "clauses" / "example-1" / "request.json").is_file()
    assert (tmp_path / "artifacts" / "clauses" / "example-1" / "response.json").is_file()


def test_resume_reuses_completed_results_and_retries_only_failures() -> None:
    examples = (
        _example(1, "These requirements apply to new systems."),
        _example(2, "This clause applies when the safety function is active."),
    )
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True, True),
    )
    first_gateway = SequenceGateway(
        {
            "applicability_target": "clause_or_requirement",
            "applicability_functions": ["inclusion"],
            "evidence": [{"function": "inclusion", "text": "new systems"}],
        },
        LlmUnavailableError("temporary outage"),
    )
    first = _service(first_gateway).enrich(selection=selection, examples=examples)
    assert first.enriched_clause_count == 1
    assert first.failed_clause_count == 1

    second_gateway = SequenceGateway(
        {
            "applicability_target": "clause_or_requirement",
            "applicability_functions": ["applicability_condition"],
            "evidence": [
                {
                    "function": "applicability_condition",
                    "text": "when the safety function is active",
                }
            ],
        }
    )
    service = _service(second_gateway)
    assert service.pending_clause_count(selection=selection, existing=first) == 1
    resumed = service.enrich(
        selection=selection,
        examples=examples,
        existing=first,
    )

    assert service.pending_clause_count(selection=selection, existing=resumed) == 0
    assert second_gateway.calls == 1
    assert resumed.failed_clause_count == 0
    assert resumed.enriched_clause_count == 2
    assert resumed.run_statistics.reused_clause_count == 1
    assert resumed.run_statistics.attempted_clause_count == 1


def test_global_review_status_does_not_filter_final_presence_positive_clause() -> None:
    examples = (_example(1, "These requirements apply to new systems."),)
    consensus = _consensus(True)
    reviewed_clause = consensus.clauses[0].model_copy(
        update={
            "requires_review": True,
            "review_reasons": ("role_relation_disagreement",),
        }
    )
    reviewed_consensus = consensus.model_copy(
        update={
            "review_count": 1,
            "clauses": (reviewed_clause,),
        }
    )

    selection = _detail_selection(
        examples=examples,
        consensus=reviewed_consensus,
    )

    assert selection.selected_clause_count == 1
    assert selection.clauses[0].source_requires_review is True


def test_evidence_grounding_preserves_source_case() -> None:
    text = "These Requirements apply to new systems."
    examples = (_example(1, text),)
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True),
    )
    gateway = SequenceGateway(
        {
            "applicability_target": "clause_or_requirement",
            "applicability_functions": ["inclusion"],
            "evidence": [{"function": "inclusion", "text": "these requirements"}],
        }
    )

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert report.clauses[0].outcome is ApplicabilityDetailOutcome.UNRESOLVED
    assert report.clauses[0].applicability_functions == ()
    assert report.clauses[0].evidence == ()
    assert report.clauses[0].evidence_grounded is True


def test_empty_positive_selection_performs_zero_inference_calls() -> None:
    examples = (_example(1, "The supplier records the result."),)
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(False),
    )
    gateway = SequenceGateway()

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert gateway.calls == 0
    assert report.selected_clause_count == 0
    assert report.processed_clause_count == 0


def test_detail_prompt_uses_positive_instruction_framing() -> None:
    root = RESOURCES / "prompts" / "applicability-detail-enrichment" / "detail-structure-aware-v1"
    prompt_text = "\n".join(
        (root / name).read_text(encoding="utf-8").casefold() for name in ("system.txt", "user.txt")
    )

    negative_instruction_tokens = (
        " do not ",
        " don't ",
        " never ",
        " without ",
        " must not ",
        " no ",
        " cannot ",
    )
    padded = f" {prompt_text} "
    assert all(token not in padded for token in negative_instruction_tokens)


def test_detail_predictions_are_canonicalized_by_taxonomy_order() -> None:
    text = "This clause applies to the system except for legacy installations."
    examples = (_example(1, text),)
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True),
    )
    gateway = SequenceGateway(
        {
            "applicability_target": "clause_or_requirement",
            "applicability_functions": ["exception", "scope_definition"],
            "evidence": [
                {"function": "exception", "text": "except for legacy installations"},
                {"function": "scope_definition", "text": "applies to the system"},
            ],
        }
    )

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert [item.value for item in report.clauses[0].applicability_functions] == [
        "scope_definition",
        "exception",
    ]
    assert [item.function.value for item in report.clauses[0].evidence] == [
        "scope_definition",
        "exception",
    ]


def test_clause_target_with_open_detail_is_unresolved() -> None:
    examples = (_example(1, "This clause applies to the referenced case."),)
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True),
    )
    gateway = SequenceGateway(
        {
            "applicability_target": "clause_or_requirement",
            "applicability_functions": [],
            "evidence": [],
        }
    )

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert report.clauses[0].outcome is ApplicabilityDetailOutcome.UNRESOLVED
    assert report.clauses[0].applicability_target.value == "clause_or_requirement"


def test_non_clause_applicability_targets_are_reclassified_as_not_confirmed() -> None:
    texts = (
        "This calculation method can be applied to matching device families.",
        "This activity applies during integration.",
        "This component is applicable to high-voltage systems.",
        "This guidance applies to another semantic target.",
        "The supplier records the result.",
    )
    examples = tuple(_example(index, text) for index, text in enumerate(texts, start=1))
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True, True, True, True, True),
    )
    gateway = SequenceGateway(
        *[
            {
                "applicability_target": target,
                "applicability_functions": [],
                "evidence": [],
            }
            for target in (
                "method_or_technique",
                "process_or_activity",
                "object_or_component",
                "other",
                "none",
            )
        ]
    )

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert report.not_confirmed_clause_count == 5
    assert all(item.outcome is ApplicabilityDetailOutcome.NOT_CONFIRMED for item in report.clauses)
    assert [item.applicability_target.value for item in report.clauses] == [
        "method_or_technique",
        "process_or_activity",
        "object_or_component",
        "other",
        "none",
    ]
    assert all(item.evidence_grounded for item in report.clauses)


def test_non_clause_target_discards_clause_detail_classification() -> None:
    examples = (_example(1, "This calculation method can be applied to matching products."),)
    selection = _detail_selection(examples=examples, consensus=_consensus(True))
    gateway = SequenceGateway(
        {
            "applicability_target": "method_or_technique",
            "applicability_functions": ["inclusion"],
            "evidence": [{"function": "inclusion", "text": "matching products"}],
        }
    )

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert report.failed_clause_count == 0
    assert report.not_confirmed_clause_count == 1
    assert report.clauses[0].outcome is ApplicabilityDetailOutcome.NOT_CONFIRMED
    assert report.clauses[0].applicability_target.value == "method_or_technique"
    assert report.clauses[0].applicability_functions == ()
    assert report.clauses[0].evidence == ()
    assert report.clauses[0].evidence_grounded is True


def test_clause_target_prunes_unsupported_functions_and_evidence() -> None:
    text = "This clause applies to new systems except for legacy installations."
    examples = (_example(1, text),)
    selection = _detail_selection(examples=examples, consensus=_consensus(True))
    gateway = SequenceGateway(
        {
            "applicability_target": "clause_or_requirement",
            "applicability_functions": ["inclusion", "exclusion", "exception"],
            "evidence": [
                {"function": "inclusion", "text": "applies to new systems"},
                {"function": "exception", "text": "except for legacy installations"},
                {"function": "scope_definition", "text": "new systems"},
                {"function": "exclusion", "text": "text that is absent"},
            ],
        }
    )

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert report.failed_clause_count == 0
    assert report.enriched_clause_count == 1
    assert [item.value for item in report.clauses[0].applicability_functions] == [
        "inclusion",
        "exception",
    ]
    assert [item.function.value for item in report.clauses[0].evidence] == [
        "inclusion",
        "exception",
    ]
    assert report.clauses[0].evidence_grounded is True


def test_clause_target_deduplicates_supported_prediction_detail() -> None:
    text = "These requirements apply to new systems."
    examples = (_example(1, text),)
    selection = _detail_selection(examples=examples, consensus=_consensus(True))
    gateway = SequenceGateway(
        {
            "applicability_target": "clause_or_requirement",
            "applicability_functions": ["inclusion", "inclusion"],
            "evidence": [
                {"function": "inclusion", "text": "apply to new systems"},
                {"function": "inclusion", "text": "apply to new systems"},
            ],
        }
    )

    report = _service(gateway).enrich(selection=selection, examples=examples)

    assert report.failed_clause_count == 0
    assert report.enriched_clause_count == 1
    assert [item.value for item in report.clauses[0].applicability_functions] == ["inclusion"]
    assert len(report.clauses[0].evidence) == 1


def test_selection_rejects_content_hash_mismatch() -> None:
    example = _example(1, "This clause applies to the system.")
    corrupted = EvaluationExample(
        id=example.id,
        input={
            "content": {"text": "This clause applies to the system.", "hash": "sha256:" + "0" * 64},
            "context": example.input["context"],
        },
        expected={},
    )

    with pytest.raises(ValueError, match="content hash differs"):
        _detail_selection(
            examples=(corrupted,),
            consensus=_consensus(True),
        )


def test_v2_prompt_uses_independent_clause_and_other_target_decisions() -> None:
    prompt = PromptRepository(RESOURCES / "prompts").load(
        "applicability-detail-enrichment", "detail-structure-aware-v2"
    )

    assert "two independent decisions" in prompt.system_prompt
    assert "There is no dominant-target or priority rule" in prompt.system_prompt
    assert "technical conditions, prerequisites, guards, thresholds" in prompt.system_prompt
    assert "merely referring to another clause or requirement" in prompt.system_prompt
    assert prompt.output_schema["properties"]["contains_clause_or_requirement_applicability"] == {
        "type": "boolean"
    }
    assert prompt.output_schema["properties"]["other_applicability_targets"]["items"]["enum"] == [
        "method_or_technique",
        "process_or_activity",
        "object_or_component",
        "other",
    ]


def test_v3_prompt_calibrates_gate_against_moving_golden_archetypes() -> None:
    v2 = PromptRepository(RESOURCES / "prompts").load(
        "applicability-detail-enrichment", "detail-structure-aware-v2"
    )
    v3 = PromptRepository(RESOURCES / "prompts").load(
        "applicability-detail-enrichment", "detail-structure-aware-v3"
    )
    fixture = json.loads(
        Path("tests/fixtures/applicability/detail-v3-moving-golden-cases.json").read_text(
            encoding="utf-8"
        )
    )

    cases = fixture["cases"]
    assert len(cases) == 9
    assert sum(item["v2_transition"] == "wrong_to_correct" for item in cases) == 4
    assert sum(item["v2_transition"] == "correct_to_wrong" for item in cases) == 5
    assert v3.output_schema == v2.output_schema
    assert v3.user_template == v2.user_template
    assert "conditions are not automatically applicability" in v3.system_prompt
    assert "Do not use one decision as evidence for the other" in v3.system_prompt
    assert 'Do not use "mixed" as a fallback for uncertainty' in v3.system_prompt

    for archetype in {item["prompt_archetype"] for item in cases}:
        assert archetype in v3.system_prompt

    # Keep the calibration structural rather than leaking Golden clause identities into the prompt.
    for document_key in {item["document_key"] for item in cases}:
        assert document_key not in v3.system_prompt


def test_v3_prompt_preserves_true_mixed_and_false_method_only_contrasts() -> None:
    prompt = PromptRepository(RESOURCES / "prompts").load(
        "applicability-detail-enrichment", "detail-structure-aware-v3"
    )

    assert (
        '"These requirements apply throughout development and are also applicable to the '
        'constituent functions."' in prompt.system_prompt
    )
    assert (
        '"If a technique not listed in the tables is proposed, its effectiveness and '
        'suitability shall be justified."' in prompt.system_prompt
    )
    assert (
        '"If applicable, an evaluation of the applied tailoring shall be performed."'
        in prompt.system_prompt
    )
    assert "technical credit is admissible" in prompt.system_prompt
    assert "the condition changes its execution" in prompt.system_prompt


def test_v4_prompt_balances_v3_regressions_with_normative_consequence_test() -> None:
    v3 = PromptRepository(RESOURCES / "prompts").load(
        "applicability-detail-enrichment", "detail-structure-aware-v3"
    )
    v4 = PromptRepository(RESOURCES / "prompts").load(
        "applicability-detail-enrichment", "detail-structure-aware-v4"
    )
    fixture = json.loads(
        Path("tests/fixtures/applicability/detail-v4-v3-calibration-cases.json").read_text(
            encoding="utf-8"
        )
    )

    cases = fixture["cases"]
    assert len(cases) == 14
    assert sum(item["v3_transition"] == "wrong_to_correct" for item in cases) == 8
    assert sum(item["v3_transition"] == "correct_to_wrong" for item in cases) == 6
    assert v4.output_schema == v3.output_schema
    assert v4.user_template == v3.user_template
    assert "normative-consequence test" in v4.system_prompt
    assert "Judge the normative consequence, not the grammatical subject" in v4.system_prompt
    assert (
        "If removing the statement would change whether a normative provision" in v4.system_prompt
    )
    assert "Eligibility or achievement condition" in v4.system_prompt
    assert "Applicability adjective attached to an engineering artifact" in v4.system_prompt

    for archetype in {item["prompt_archetype"] for item in cases}:
        assert archetype in v4.system_prompt

    # Keep the calibration structural rather than leaking Golden clause identities into the prompt.
    for document_key in {item["document_key"] for item in cases}:
        assert document_key not in v4.system_prompt


def test_v4_prompt_preserves_waivers_scope_and_technical_negative_contrasts() -> None:
    prompt = PromptRepository(RESOURCES / "prompts").load(
        "applicability-detail-enrichment", "detail-structure-aware-v4"
    )

    assert (
        '"Items assigned class Q have no requirement to comply with Part 5."'
        in prompt.system_prompt
    )
    assert (
        '"If the event is assigned exposure class N, no integrity-level assignment is required."'
        in prompt.system_prompt
    )
    assert (
        '"This standard applies to programmable controllers irrespective of their '
        'application sector."' in prompt.system_prompt
    )
    assert (
        '"For qualified status to be obtained, the evaluation period shall demonstrate the '
        'specified target."' in prompt.system_prompt
    )
    assert '"All applicable work products are provided for integration."' in prompt.system_prompt
    assert 'does not need to use "this clause applies"' in prompt.system_prompt
    assert "secondary target neither proves nor disproves Decision 1" in prompt.system_prompt


def test_v2_prediction_preserves_mixed_clause_and_method_applicability() -> None:
    content = (
        "These requirements apply to replacement systems. "
        "The diagnostic method may also be used for replacement systems."
    )

    prediction = parse_applicability_detail_prediction_v2(
        {
            "contains_clause_or_requirement_applicability": True,
            "other_applicability_targets": ["method_or_technique"],
            "applicability_functions": ["inclusion"],
            "evidence": [
                {
                    "function": "inclusion",
                    "text": "requirements apply to replacement systems",
                }
            ],
        },
        content=content,
    )

    assert prediction.contains_clause_or_requirement_applicability is True
    assert [item.value for item in prediction.other_applicability_targets] == [
        "method_or_technique"
    ]
    assert [item.value for item in prediction.applicability_functions] == ["inclusion"]
    assert len(prediction.evidence) == 1


def test_v2_prediction_keeps_non_clause_target_but_clears_clause_detail() -> None:
    content = "The calculation method may be used when the input data are complete."

    prediction = parse_applicability_detail_prediction_v2(
        {
            "contains_clause_or_requirement_applicability": False,
            "other_applicability_targets": ["method_or_technique"],
            "applicability_functions": ["applicability_condition"],
            "evidence": [
                {
                    "function": "applicability_condition",
                    "text": "when the input data are complete",
                }
            ],
        },
        content=content,
    )

    assert prediction.contains_clause_or_requirement_applicability is False
    assert [item.value for item in prediction.other_applicability_targets] == [
        "method_or_technique"
    ]
    assert prediction.applicability_functions == ()
    assert prediction.evidence == ()


def test_v2_prediction_represents_presence_false_positive_without_none_target() -> None:
    prediction = parse_applicability_detail_prediction_v2(
        {
            "contains_clause_or_requirement_applicability": False,
            "other_applicability_targets": [],
            "applicability_functions": [],
            "evidence": [],
        },
        content="The supplier records the result.",
    )

    assert prediction.contains_clause_or_requirement_applicability is False
    assert prediction.other_applicability_targets == ()
    assert prediction.applicability_functions == ()
    assert prediction.evidence == ()


def test_v2_prediction_rejects_clause_target_inside_other_targets() -> None:
    with pytest.raises(ValueError, match="other_applicability_targets"):
        parse_applicability_detail_prediction_v2(
            {
                "contains_clause_or_requirement_applicability": True,
                "other_applicability_targets": ["clause_or_requirement"],
                "applicability_functions": [],
                "evidence": [],
            },
            content="These requirements apply to the subsystem.",
        )


def test_v2_prediction_deduplicates_other_targets_and_prunes_ungrounded_detail() -> None:
    content = "These requirements apply to new systems and a verification method may be used."

    prediction = parse_applicability_detail_prediction_v2(
        {
            "contains_clause_or_requirement_applicability": True,
            "other_applicability_targets": [
                "method_or_technique",
                "method_or_technique",
            ],
            "applicability_functions": ["inclusion", "exception"],
            "evidence": [
                {"function": "inclusion", "text": "requirements apply to new systems"},
                {"function": "exception", "text": "legacy systems are excepted"},
            ],
        },
        content=content,
    )

    assert [item.value for item in prediction.other_applicability_targets] == [
        "method_or_technique"
    ]
    assert [item.value for item in prediction.applicability_functions] == ["inclusion"]
    assert [item.function.value for item in prediction.evidence] == ["inclusion"]


def test_reused_detail_selection_keeps_original_fingerprint_across_contract_experiment() -> None:
    examples = (
        _example(1, "These requirements apply to replacement systems."),
        _example(2, "The supplier records the result."),
    )
    run_selection = _selection(2)
    consensus = _consensus(True, False)
    coverage = build_qualification_coverage(selection=run_selection, report=consensus)
    original = build_applicability_detail_selection(
        run_selection=run_selection,
        examples=examples,
        consensus=consensus,
        coverage=coverage,
        task_version="1.0.0",
    )

    reused = validate_reused_applicability_detail_selection(
        persisted_selection=original,
        run_selection=run_selection,
        examples=examples,
        consensus=consensus,
        coverage=coverage,
    )

    assert reused is original
    assert reused.task_version == "1.0.0"
    assert reused.fingerprint == original.fingerprint


def test_reused_detail_selection_rejects_changed_presence_projection() -> None:
    examples = (_example(1, "These requirements apply to replacement systems."),)
    run_selection = _selection(1)
    positive_consensus = _consensus(True)
    original = build_applicability_detail_selection(
        run_selection=run_selection,
        examples=examples,
        consensus=positive_consensus,
        coverage=build_qualification_coverage(
            selection=run_selection,
            report=positive_consensus,
        ),
        task_version="1.0.0",
    )
    negative_consensus = _consensus(False)

    with pytest.raises(ValueError, match="persisted applicability detail selection differs"):
        validate_reused_applicability_detail_selection(
            persisted_selection=original,
            run_selection=run_selection,
            examples=examples,
            consensus=negative_consensus,
            coverage=build_qualification_coverage(
                selection=run_selection,
                report=negative_consensus,
            ),
        )


def test_v2_service_uses_boolean_gate_and_preserves_mixed_targets() -> None:
    texts = (
        (
            "These requirements apply to replacement systems. "
            "The diagnostic method may also be used for replacement systems."
        ),
        "The calculation method may be used when the input data are complete.",
        "The supplier records the result.",
    )
    examples = tuple(_example(index, text) for index, text in enumerate(texts, start=1))
    selection = _detail_selection(
        examples=examples,
        consensus=_consensus(True, True, True),
    )
    gateway = SequenceGateway(
        {
            "contains_clause_or_requirement_applicability": True,
            "other_applicability_targets": ["method_or_technique"],
            "applicability_functions": ["inclusion"],
            "evidence": [
                {
                    "function": "inclusion",
                    "text": "requirements apply to replacement systems",
                }
            ],
        },
        {
            "contains_clause_or_requirement_applicability": False,
            "other_applicability_targets": ["method_or_technique"],
            "applicability_functions": [],
            "evidence": [],
        },
        {
            "contains_clause_or_requirement_applicability": False,
            "other_applicability_targets": [],
            "applicability_functions": [],
            "evidence": [],
        },
    )

    report = _service_v2(gateway).enrich(selection=selection, examples=examples)

    assert report.task_version == "2.0.0"
    assert report.prompt_version == "detail-structure-aware-v2"
    assert [item.outcome for item in report.clauses] == [
        ApplicabilityDetailOutcome.ENRICHED,
        ApplicabilityDetailOutcome.NOT_CONFIRMED,
        ApplicabilityDetailOutcome.NOT_CONFIRMED,
    ]
    mixed = report.clauses[0]
    assert mixed.contains_clause_or_requirement_applicability is True
    assert mixed.applicability_target.value == "clause_or_requirement"
    assert [item.value for item in mixed.other_applicability_targets] == ["method_or_technique"]
    method_only = report.clauses[1]
    assert method_only.contains_clause_or_requirement_applicability is False
    assert method_only.applicability_target.value == "method_or_technique"
    assert [item.value for item in method_only.other_applicability_targets] == [
        "method_or_technique"
    ]
    no_target = report.clauses[2]
    assert no_target.contains_clause_or_requirement_applicability is False
    assert no_target.applicability_target.value == "none"
    assert no_target.other_applicability_targets == ()


def test_v2_service_uses_clause_boolean_not_secondary_target_as_gate() -> None:
    content = (
        "These requirements apply to replacement systems. "
        "A diagnostic method may be used for the same systems."
    )
    examples = (_example(1, content),)
    selection = _detail_selection(examples=examples, consensus=_consensus(True))
    gateway = SequenceGateway(
        {
            "contains_clause_or_requirement_applicability": True,
            "other_applicability_targets": ["method_or_technique"],
            "applicability_functions": ["inclusion"],
            "evidence": [
                {
                    "function": "inclusion",
                    "text": "requirements apply to replacement systems",
                }
            ],
        }
    )

    report = _service_v2(gateway).enrich(selection=selection, examples=examples)

    assert report.enriched_clause_count == 1
    assert report.not_confirmed_clause_count == 0
    assert report.clauses[0].contains_clause_or_requirement_applicability is True
    assert [item.value for item in report.clauses[0].other_applicability_targets] == [
        "method_or_technique"
    ]
