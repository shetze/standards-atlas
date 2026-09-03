"""Model and prompt qualification matrices for semantic annotation runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    ApplicabilityDetailEnrichmentConfig,
)
from standards_atlas.application.semantic_qualification.qualification import (
    AnnotationQualificationReport,
)
from standards_atlas.application.semantic_qualification.reports.matrix import (
    render_qualification_matrix_markdown,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_qualification import (
    SemanticExtractionQualificationConfig,
)

_PROMPT_VERSION_ALIASES = {
    "content-only": "content-only-v1",
    "structure-aware": "structure-aware-v1",
    "reference-aware": "evidence-first-v1",
    "bounded-reasoning": "bounded-reasoning-v1",
    "deliberative": "bounded-reasoning-v1",
}


class PromptCandidate(BaseModel):
    """One versioned prompt variant in the qualification shortlist."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    description: str = ""
    definition: Path | None = None
    prompt_version: str | None = None
    max_output_tokens: int = Field(default=512, gt=0)
    adaptive_interview: bool = False
    cbox_frame: str = "full-context-v1"

    @field_validator("cbox_frame")
    @classmethod
    def _validate_cbox_frame(cls, value: str) -> str:
        from standards_atlas.application.semantic_qualification.context_framing import (
            resolve_cbox_frame_policy,
        )

        resolve_cbox_frame_policy(value)
        return value


def resolve_prompt_version(
    prompt: PromptCandidate,
    *,
    resources: Path,
    task: str = "semantic-profile-classification",
) -> str:
    """Resolve a matrix prompt id to an installed prompt resource version."""
    candidates = [prompt.prompt_version, _PROMPT_VERSION_ALIASES.get(prompt.id), prompt.id]
    checked: list[str] = []
    for candidate in candidates:
        if not candidate or candidate in checked:
            continue
        checked.append(candidate)
        task_roots = [resources / "prompts" / task]
        if task == "semantic-profile-classification":
            task_roots.append(resources / "prompts" / "statement-function-classification")
        if any((root / candidate / "prompt.json").is_file() for root in task_roots):
            return candidate
    available_root = resources / "prompts" / task
    if not available_root.is_dir() and task == "semantic-profile-classification":
        available_root = resources / "prompts" / "statement-function-classification"
    available = (
        sorted(path.name for path in available_root.iterdir() if path.is_dir())
        if available_root.is_dir()
        else []
    )
    raise ValueError(
        f"prompt {prompt.id!r} cannot be resolved; checked {checked}; "
        f"available versions: {available}"
    )


class ModelGenerationConfig(BaseModel):
    """Model-specific generation budgets and reasoning defaults."""

    model_config = ConfigDict(frozen=True)

    max_output_tokens: int | None = Field(default=None, gt=0)
    adaptive_question_max_tokens: int | None = Field(default=None, gt=0)
    truncation_retry_max_tokens: int | None = Field(default=None, gt=0)
    reasoning_mode: str = Field(default="disabled", pattern="^(disabled|enabled)$")
    retry_on_truncation: bool = True

    @model_validator(mode="after")
    def validate_retry_budget(self) -> ModelGenerationConfig:
        if (
            self.max_output_tokens is not None
            and self.truncation_retry_max_tokens is not None
            and self.truncation_retry_max_tokens < self.max_output_tokens
        ):
            raise ValueError(
                "truncation_retry_max_tokens must not be smaller than max_output_tokens"
            )
        return self


class CascadeResolutionConfig(BaseModel):
    """Rules used to decide whether a clause needs escalation."""

    model_config = ConfigDict(frozen=True)

    minimum_successful_models: int = Field(default=3, ge=1)
    minimum_applicability_presence_models: int | None = Field(default=None, ge=1)
    accepted_categories: tuple[str, ...] = (
        "unanimous",
        "strong_consensus",
        "majority_consensus",
    )
    minimum_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    escalate_on_knowledge_kind_disagreement: bool = True
    minimum_knowledge_kind_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    escalate_on_applicability_disagreement: bool = True
    escalate_on_applicability_presence_disagreement: bool | None = None
    escalate_on_role_relation_disagreement: bool = True
    minimum_applicability_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    minimum_applicability_presence_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    minimum_role_relation_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    statement_function_resolution_mode: Literal["cumulative", "stage_resolver"] = "cumulative"
    statement_function_resolver_min_confidence: float = Field(default=0.75, ge=0.0, le=1.0)


def effective_cascade_resolution(
    resolution: CascadeResolutionConfig,
    *,
    review_majority_min_confidence: float,
) -> CascadeResolutionConfig:
    """Align cascade finalization with downstream review acceptance.

    A statement-function majority must not be frozen as resolved when the
    configured review policy would deterministically send the same confidence
    to HITL. The manifest remains unchanged; this returns the auditable
    effective policy used for execution.
    """
    return resolution.model_copy(
        update={
            "minimum_confidence": max(
                resolution.minimum_confidence,
                review_majority_min_confidence,
            )
        }
    )


class CascadeStage(BaseModel):
    """One ordered model and prompt stage in cascade execution."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    models: tuple[str, ...] = Field(min_length=1)
    prompts: tuple[str, ...] = ()
    apply_to: str = Field(default="all", pattern="^(all|unresolved)$")
    resolution: CascadeResolutionConfig | None = None


def cascade_escalation_reasons(
    clause: object, resolution: CascadeResolutionConfig
) -> tuple[str, ...]:
    """Return dimension-aware reasons why a clause must enter the next stage."""
    reasons: list[str] = []
    accepted = set(resolution.accepted_categories)
    if clause.participating_models < resolution.minimum_successful_models:
        reasons.append("insufficient_models")
    if clause.category.value not in accepted:
        reasons.append("consensus_category")
    if clause.statement_function_confidence < resolution.minimum_confidence:
        reasons.append("statement_function_confidence")
    knowledge_threshold = resolution.minimum_knowledge_kind_confidence
    if knowledge_threshold is not None:
        if getattr(clause, "knowledge_kind_decision_confidence", 1.0) < knowledge_threshold:
            reasons.append("knowledge_kind_confidence")
    elif resolution.escalate_on_knowledge_kind_disagreement and not getattr(
        clause, "knowledge_primary_unanimous", True
    ):
        reasons.append("knowledge_kind_disagreement")
    applicability_minimum_models = (
        resolution.minimum_applicability_presence_models or resolution.minimum_successful_models
    )
    if _applicability_presence_model_count(clause) < applicability_minimum_models:
        reasons.append("insufficient_applicability_presence_models")
    applicability_threshold = _applicability_presence_threshold(resolution)
    if applicability_threshold is not None:
        if _applicability_presence_confidence(clause) < applicability_threshold:
            reasons.append("applicability_presence_confidence")
    elif _escalate_on_applicability_presence_disagreement(resolution) and not getattr(
        clause, "applicability_presence_unanimous", clause.applicability_unanimous
    ):
        reasons.append("applicability_presence_disagreement")
    if getattr(clause, "role_semantics_evidence_conflict", False):
        reasons.append("role_semantics_evidence_conflict")
    role_unanimous = getattr(clause, "role_semantics_unanimous", clause.role_relation_unanimous)
    if resolution.escalate_on_role_relation_disagreement and not role_unanimous:
        reasons.append("role_relation_disagreement")

    role_relation_threshold = resolution.minimum_role_relation_confidence
    if role_relation_threshold is not None:
        role_presence_confidence = getattr(
            clause,
            "role_semantics_presence_confidence",
            getattr(
                clause,
                "role_relation_decision_confidence",
                _dimension_decision_confidence(
                    present=clause.role_relation_present,
                    positive_confidence=clause.role_relation_confidence,
                    support=clause.role_relation_support,
                ),
            ),
        )
        if role_presence_confidence < role_relation_threshold:
            reasons.append("role_relation_confidence")
    return tuple(reasons)


def cascade_unresolved_clause_ids(
    clauses: tuple[object, ...] | list[object],
    *,
    stage_clause_ids: tuple[str, ...],
    resolution: CascadeResolutionConfig,
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Resolve only clauses that actually participated in the current cascade stage."""
    stage_id_set = set(stage_clause_ids)
    escalation_reasons = {
        clause.clause_id: cascade_escalation_reasons(clause, resolution)
        for clause in clauses
        if clause.clause_id in stage_id_set
    }
    unresolved = tuple(
        clause_id for clause_id in stage_clause_ids if escalation_reasons.get(clause_id)
    )
    return unresolved, escalation_reasons


def cascade_stage_escalation_reasons(
    *,
    cumulative_clause: object,
    stage_clause: object,
    previous_reasons: tuple[str, ...],
    resolution: CascadeResolutionConfig,
) -> tuple[str, ...]:
    """Re-evaluate only dimensions that were unresolved before this stage.

    Statement function can use a stage-local resolver, while applicability and
    role relations continue to use cumulative evidence. Resolved dimensions
    never become unresolved again merely because later models disagree.
    """
    unresolved = set(previous_reasons)
    reasons: list[str] = []

    if "insufficient_models" in unresolved:
        if cumulative_clause.participating_models < resolution.minimum_successful_models:
            reasons.append("insufficient_models")

    statement_unresolved = bool(
        unresolved & {"consensus_category", "statement_function_confidence"}
    )
    if statement_unresolved:
        if resolution.statement_function_resolution_mode == "stage_resolver":
            if (
                stage_clause.statement_function_confidence
                < resolution.statement_function_resolver_min_confidence
            ):
                reasons.append("statement_function_resolver_confidence")
        else:
            accepted = set(resolution.accepted_categories)
            if cumulative_clause.category.value not in accepted:
                reasons.append("consensus_category")
            if cumulative_clause.statement_function_confidence < resolution.minimum_confidence:
                reasons.append("statement_function_confidence")

    knowledge_unresolved = bool(unresolved & _KNOWLEDGE_REASONS)
    if knowledge_unresolved:
        threshold = resolution.minimum_knowledge_kind_confidence
        if threshold is not None:
            if getattr(cumulative_clause, "knowledge_kind_decision_confidence", 1.0) < threshold:
                reasons.append("knowledge_kind_confidence")
        elif resolution.escalate_on_knowledge_kind_disagreement and not getattr(
            cumulative_clause, "knowledge_primary_unanimous", True
        ):
            reasons.append("knowledge_kind_disagreement")

    applicability_unresolved = bool(unresolved & _APPLICABILITY_REASONS)
    if applicability_unresolved:
        applicability_minimum_models = (
            resolution.minimum_applicability_presence_models or resolution.minimum_successful_models
        )
        if (
            "insufficient_applicability_presence_models" in unresolved
            and _applicability_presence_model_count(cumulative_clause)
            < applicability_minimum_models
        ):
            reasons.append("insufficient_applicability_presence_models")
        threshold = _applicability_presence_threshold(resolution)
        if threshold is not None:
            if _applicability_presence_confidence(cumulative_clause) < threshold:
                reasons.append("applicability_presence_confidence")
        elif _escalate_on_applicability_presence_disagreement(resolution) and not getattr(
            cumulative_clause,
            "applicability_presence_unanimous",
            cumulative_clause.applicability_unanimous,
        ):
            reasons.append("applicability_presence_disagreement")

    role_relation_unresolved = bool(
        unresolved
        & {
            "role_relation_disagreement",
            "role_relation_confidence",
            "role_semantics_disagreement",
            "role_semantics_confidence",
            "role_semantics_evidence_conflict",
        }
    )
    if role_relation_unresolved:
        if "role_semantics_evidence_conflict" in unresolved and getattr(
            cumulative_clause, "role_semantics_evidence_conflict", False
        ):
            reasons.append("role_semantics_evidence_conflict")
        threshold = resolution.minimum_role_relation_confidence
        if threshold is not None:
            confidence = getattr(
                cumulative_clause,
                "role_semantics_presence_confidence",
                getattr(
                    cumulative_clause,
                    "role_relation_decision_confidence",
                    _dimension_decision_confidence(
                        present=cumulative_clause.role_relation_present,
                        positive_confidence=cumulative_clause.role_relation_confidence,
                        support=cumulative_clause.role_relation_support,
                    ),
                ),
            )
            if confidence < threshold:
                reasons.append("role_relation_confidence")
        elif resolution.escalate_on_role_relation_disagreement and not getattr(
            cumulative_clause,
            "role_semantics_unanimous",
            cumulative_clause.role_relation_unanimous,
        ):
            reasons.append("role_relation_disagreement")

    return tuple(reasons)


def cascade_stage_unresolved_clause_ids(
    cumulative_clauses: tuple[object, ...] | list[object],
    stage_clauses: tuple[object, ...] | list[object],
    *,
    stage_clause_ids: tuple[str, ...],
    previous_reasons: dict[str, tuple[str, ...]],
    resolution: CascadeResolutionConfig,
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Resolve one later cascade stage with dimension-level monotonicity."""
    cumulative_by_id = {clause.clause_id: clause for clause in cumulative_clauses}
    stage_by_id = {clause.clause_id: clause for clause in stage_clauses}
    reasons = {
        clause_id: cascade_stage_escalation_reasons(
            cumulative_clause=cumulative_by_id[clause_id],
            stage_clause=stage_by_id[clause_id],
            previous_reasons=previous_reasons.get(clause_id, ()),
            resolution=resolution,
        )
        for clause_id in stage_clause_ids
        if clause_id in cumulative_by_id and clause_id in stage_by_id
    }
    unresolved = tuple(clause_id for clause_id in stage_clause_ids if reasons.get(clause_id))
    return unresolved, reasons


def _dimension_decision_confidence(
    *, present: bool, positive_confidence: float, support: dict[str, float]
) -> float:
    if present:
        return positive_confidence
    return max(0.0, 1.0 - float(support.get("present", 0.0)))


def _applicability_presence_model_count(clause: object) -> int:
    configured = getattr(clause, "applicability_participating_models", None)
    if configured is not None:
        return int(configured)
    votes = getattr(clause, "votes", ())
    if votes:
        return sum(
            bool(getattr(vote, "applicability_presence_eligible", True))
            for vote in votes
            if getattr(vote, "role", "voter") == "voter"
        )
    return int(getattr(clause, "participating_models", 0))


def _applicability_presence_confidence(clause: object) -> float:
    return float(
        getattr(
            clause,
            "applicability_presence_confidence",
            getattr(
                clause,
                "applicability_decision_confidence",
                _dimension_decision_confidence(
                    present=clause.applicability_present,
                    positive_confidence=clause.applicability_confidence,
                    support=clause.applicability_support,
                ),
            ),
        )
    )


def _escalate_on_applicability_presence_disagreement(
    resolution: CascadeResolutionConfig,
) -> bool:
    configured = resolution.escalate_on_applicability_presence_disagreement
    return resolution.escalate_on_applicability_disagreement if configured is None else configured


def _applicability_presence_threshold(
    resolution: CascadeResolutionConfig,
) -> float | None:
    configured = resolution.minimum_applicability_presence_confidence
    return resolution.minimum_applicability_confidence if configured is None else configured


_STATEMENT_REASONS = {
    "consensus_category",
    "statement_function_confidence",
    "statement_function_resolver_confidence",
}
_KNOWLEDGE_REASONS = {"knowledge_kind_disagreement", "knowledge_kind_confidence"}
_APPLICABILITY_REASONS = {
    "insufficient_applicability_presence_models",
    "applicability_presence_disagreement",
    "applicability_presence_confidence",
}
_ROLE_RELATION_REASONS = {
    "role_relation_disagreement",
    "role_relation_confidence",
    "role_semantics_evidence_conflict",
}


def capture_resolved_dimensions(
    *,
    cumulative_clause: object,
    stage_clause: object,
    previous_reasons: tuple[str, ...],
    remaining_reasons: tuple[str, ...],
    source: str,
    initial_stage: bool = False,
) -> dict[str, dict[str, Any]]:
    """Capture semantic decisions that became final in one cascade stage.

    Later stages may add evidence only for dimensions that remain unresolved.
    Persisting these snapshots makes the monotonic cascade semantics survive the
    final all-observations report.
    """
    previous = set(previous_reasons)
    remaining = set(remaining_reasons)
    result: dict[str, dict[str, Any]] = {}

    def resolved(reason_set: set[str]) -> bool:
        if initial_stage:
            return not bool(remaining & reason_set)
        return bool(previous & reason_set) and not bool(remaining & reason_set)

    if resolved(_STATEMENT_REASONS):
        clause = stage_clause
        result["statement_function"] = {
            "value": (
                clause.primary_function.value if clause.primary_function is not None else None
            ),
            "confidence": clause.statement_function_confidence,
            "category": clause.statement_function_category.value,
            "source": source,
        }
    if resolved(_KNOWLEDGE_REASONS):
        result["knowledge_kind"] = {
            "value": (
                cumulative_clause.primary_knowledge_kind.value
                if cumulative_clause.primary_knowledge_kind is not None
                else None
            ),
            "confidence": cumulative_clause.knowledge_kind_decision_confidence,
            "category": getattr(
                cumulative_clause,
                "knowledge_primary_category",
                cumulative_clause.knowledge_kind_category,
            ).value,
            "source": source,
        }
    if resolved(_APPLICABILITY_REASONS):
        result["applicability"] = {
            "present": cumulative_clause.applicability_present,
            "confidence": cumulative_clause.applicability_decision_confidence,
            "presence_confidence": getattr(
                cumulative_clause,
                "applicability_presence_confidence",
                cumulative_clause.applicability_decision_confidence,
            ),
            "category": cumulative_clause.applicability_category.value,
            "source": source,
        }
    if resolved(_ROLE_RELATION_REASONS):
        result["role_relation"] = {
            "present": cumulative_clause.role_relation_present,
            "confidence": cumulative_clause.role_relation_decision_confidence,
            "category": cumulative_clause.role_relation_category.value,
            "source": source,
        }
    return result


class MatrixExecutionConfig(BaseModel):
    """Execution strategy shared by full and cascade qualification runs."""

    model_config = ConfigDict(frozen=True)

    mode: str = Field(default="full_matrix", pattern="^(full_matrix|cascade)$")
    stages: tuple[CascadeStage, ...] = ()
    resolution: CascadeResolutionConfig = CascadeResolutionConfig()


class ModelDimensionEligibility(BaseModel):
    """Dimension-level voting eligibility for one model candidate."""

    model_config = ConfigDict(frozen=True)

    applicability_presence: bool = True


class ModelCandidate(BaseModel):
    """One model/provider combination and its declared resource profile."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_ref: str | None = None
    quantization: str | None = None
    description: str = ""
    accelerator: str | None = None
    parameters_billion: float | None = Field(default=None, gt=0.0)
    declared_memory_gb: float | None = Field(default=None, gt=0.0)
    repetitions: int | None = Field(default=None, ge=0)
    supported_reasoning_modes: tuple[str, ...] = ("disabled",)
    dimension_eligibility: ModelDimensionEligibility = ModelDimensionEligibility()
    generation: ModelGenerationConfig = ModelGenerationConfig()


class ReasoningMode(BaseModel):
    """Optional reasoning configuration evaluated as a third matrix dimension."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    enabled: bool = False
    optional: bool = False
    description: str = ""


class MatrixObservation(BaseModel):
    """One repeated model/prompt run and its 5.4.5 qualification report."""

    model_config = ConfigDict(frozen=True)

    prompt_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    reasoning_mode_id: str = "disabled"
    repetition: int = Field(ge=1)
    qualification_report: Path
    run_directory: Path | None = None
    mean_duration_seconds: float | None = Field(default=None, ge=0.0)
    elapsed_duration_seconds: float | None = Field(default=None, ge=0.0)
    performance_measurement_source: str = "legacy"
    fresh_prediction_count: int | None = Field(default=None, ge=0)
    cached_prediction_count: int = Field(default=0, ge=0)
    reused_prediction_count: int = Field(default=0, ge=0)
    peak_memory_gb: float | None = Field(default=None, ge=0.0)


class RegressionThresholds(BaseModel):
    """Project-owned acceptance thresholds for qualification candidates."""

    model_config = ConfigDict(frozen=True)

    min_gold_f1: float = Field(default=0.0, ge=0.0, le=1.0)
    min_gold_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    max_gold_f1_stddev: float = Field(default=1.0, ge=0.0, le=1.0)
    min_prediction_success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    min_json_validity_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    max_truncation_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    max_mean_duration_seconds: float | None = Field(default=None, gt=0.0)
    max_peak_memory_gb: float | None = Field(default=None, gt=0.0)
    baseline_prompt_id: str | None = None
    baseline_model_id: str | None = None
    baseline_reasoning_mode_id: str = "disabled"
    max_gold_f1_drop: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_complete_baseline(self) -> RegressionThresholds:
        if bool(self.baseline_prompt_id) != bool(self.baseline_model_id):
            raise ValueError("baseline_prompt_id and baseline_model_id must be set together")
        return self


class ReviewImportConfig(BaseModel):
    """Existing HITL review imported before matrix execution."""

    model_config = ConfigDict(frozen=True)

    run_directory: Path
    review_directory: Path
    local_corpus_root: Path = Path(".atlas/data/evaluation/corpora")
    overwrite: bool = False
    required: bool = True


class ReviewPolicyConfig(BaseModel):
    """Risk-based policy deciding which consensus results require HITL review."""

    model_config = ConfigDict(frozen=True)

    review_categories: tuple[str, ...] = (
        "disputed",
        "insufficient_evidence",
    )
    accept_majority_min_confidence: float = Field(default=0.67, ge=0.0, le=1.0)
    accept_majority_min_models: int = Field(default=3, ge=1)
    applicability_min_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    role_relation_min_confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    require_role_relation_evidence: bool = True


class ConsensusPromptSelection(BaseModel):
    """Prompt family used for each semantic dimension."""

    model_config = ConfigDict(frozen=True)

    statement_function: str = "content-only"
    knowledge_kind: str = "content-only"
    applicability: str = "content-only"
    role_relation: str = "content-only"


class AdjudicationConfig(BaseModel):
    """Optional model used as a tie-breaker instead of a regular equal-weight vote."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    model_id: str | None = None
    minimum_confidence: float = Field(default=0.70, ge=0.0, le=1.0)


class StructuralPriorConfig(BaseModel):
    """Deterministic priors derived from normalization context."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


class ConsensusConfig(BaseModel):
    """Cross-model consensus settings for a new Golden Corpus proposal."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    prompt_id: str = "content-only"
    reasoning_mode_id: str = "disabled"
    prompt_selection: ConsensusPromptSelection = ConsensusPromptSelection()
    min_models: int = Field(default=3, ge=2)
    strong_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    majority_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    label_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    review_policy: ReviewPolicyConfig = ReviewPolicyConfig()
    adjudication: AdjudicationConfig = AdjudicationConfig()
    structural_priors: StructuralPriorConfig = StructuralPriorConfig()
    output_directory: Path = Path("local/review/qualification/consensus")


class ChallengerGroup(BaseModel):
    """Incumbent and challenger models competing for one cascade role."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    incumbents: tuple[str, ...] = Field(min_length=1)
    challengers: tuple[str, ...] = Field(min_length=1)


class ChallengerQualificationConfig(BaseModel):
    """Optional head-to-head qualification configuration embedded in a matrix manifest."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    repetitions: int = Field(default=1, ge=1)
    models: tuple[ModelCandidate, ...] = ()
    groups: tuple[ChallengerGroup, ...] = ()

    @property
    def model_ids(self) -> tuple[str, ...]:
        result: list[str] = []
        for group in self.groups:
            for model_id in (*group.incumbents, *group.challengers):
                if model_id not in result:
                    result.append(model_id)
        return tuple(result)


class QualificationMatrixManifest(BaseModel):
    """Versioned contract for Slice 5.4.6 qualification."""

    model_config = ConfigDict(frozen=True)

    manifest_type: Literal["qualification_matrix"] = "qualification_matrix"
    schema_version: Literal["1.5"] = "1.5"
    matrix_id: str = Field(min_length=1)
    corpus_id: str = Field(min_length=1)
    task: str = Field(default="semantic-profile-classification", min_length=1)
    task_version: str = Field(default="2.1.0", min_length=1)
    dataset_version: str = Field(default="1.0.0", min_length=1)
    repetitions: int = Field(default=3, ge=1)
    prompts: tuple[PromptCandidate, ...]
    models: tuple[ModelCandidate, ...] = Field(min_length=1)
    reasoning_modes: tuple[ReasoningMode, ...] = (ReasoningMode(id="disabled"),)
    observations: tuple[MatrixObservation, ...] = ()
    review_imports: tuple[ReviewImportConfig, ...] = ()
    consensus: ConsensusConfig = ConsensusConfig()
    execution: MatrixExecutionConfig = MatrixExecutionConfig()
    thresholds: RegressionThresholds = RegressionThresholds()
    challenger_qualification: ChallengerQualificationConfig = ChallengerQualificationConfig()
    applicability_detail_enrichment: ApplicabilityDetailEnrichmentConfig = (
        ApplicabilityDetailEnrichmentConfig(enabled=False)
    )
    semantic_extraction_qualification: SemanticExtractionQualificationConfig = (
        SemanticExtractionQualificationConfig(enabled=False)
    )

    def repetitions_for(self, model: ModelCandidate) -> int:
        """Return the model-specific repetition count or the global default."""
        return model.repetitions if model.repetitions is not None else self.repetitions

    def prompts_for_stage(self, stage: CascadeStage) -> tuple[PromptCandidate, ...]:
        """Return the prompts selected for a cascade stage."""
        if not stage.prompts:
            return self.prompts
        selected = set(stage.prompts)
        return tuple(prompt for prompt in self.prompts if prompt.id in selected)

    @property
    def model_dimension_eligibility(self) -> dict[str, dict[str, bool]]:
        """Return dimension-level voting eligibility keyed by model id."""
        return {model.id: model.dimension_eligibility.model_dump() for model in self.models}

    def eligible_model_ids_for_dimension(self, dimension: str) -> tuple[str, ...]:
        """Return production model ids allowed to vote on one semantic dimension."""
        if dimension != "applicability_presence":
            raise ValueError(f"unsupported model-eligibility dimension: {dimension}")
        return tuple(
            model.id for model in self.models if getattr(model.dimension_eligibility, dimension)
        )

    def prompts_for_model(self, model_id: str) -> tuple[PromptCandidate, ...]:
        """Return the prompts configured for one model."""
        if self.execution.mode != "cascade":
            return self.prompts
        stage = next(
            (item for item in self.execution.stages if model_id in item.models),
            None,
        )
        return self.prompts if stage is None else self.prompts_for_stage(stage)

    @model_validator(mode="after")
    def validate_matrix(self) -> QualificationMatrixManifest:
        if not self.prompts:
            raise ValueError("qualification matrix must declare at least one prompt")
        prompt_ids = [item.id for item in self.prompts]
        model_ids = [item.id for item in self.models]
        reasoning_mode_ids = [item.id for item in self.reasoning_modes]
        if len(set(prompt_ids)) != len(prompt_ids):
            raise ValueError("prompt candidate ids must be unique")
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("model candidate ids must be unique")
        challenger = self.challenger_qualification
        if challenger.enabled and not challenger.groups:
            raise ValueError("enabled challenger qualification requires at least one group")
        challenger_model_ids = [item.id for item in challenger.models]
        if len(set(challenger_model_ids)) != len(challenger_model_ids):
            raise ValueError("challenger model ids must be unique")
        overlap_models = set(model_ids).intersection(challenger_model_ids)
        if overlap_models:
            raise ValueError(
                f"challenger models must not duplicate production models: {sorted(overlap_models)}"
            )
        known_challenger_models = set(model_ids).union(challenger_model_ids)
        group_ids = [group.id for group in challenger.groups]
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("challenger qualification group ids must be unique")
        for group in challenger.groups:
            overlap = set(group.incumbents).intersection(group.challengers)
            if overlap:
                raise ValueError(
                    f"challenger group {group.id} contains models on both sides: {sorted(overlap)}"
                )
            unknown = set((*group.incumbents, *group.challengers)) - known_challenger_models
            if unknown:
                raise ValueError(
                    f"unknown models in challenger group {group.id}: {sorted(unknown)}"
                )

        adjudicator = self.consensus.adjudication
        if adjudicator.enabled and adjudicator.model_id not in model_ids:
            raise ValueError(f"unknown consensus adjudicator model: {adjudicator.model_id!r}")
        detail = self.applicability_detail_enrichment
        if detail.enabled:
            if not self.consensus.enabled:
                raise ValueError("applicability detail enrichment requires enabled final consensus")
            if detail.model is None:
                raise ValueError("enabled applicability detail enrichment requires a model")
            if detail.model not in model_ids:
                raise ValueError(f"unknown applicability detail enrichment model: {detail.model!r}")
        for model in self.models:
            unknown_modes = set(model.supported_reasoning_modes) - set(reasoning_mode_ids)
            if unknown_modes:
                raise ValueError(
                    f"unknown supported_reasoning_modes for {model.id}: {sorted(unknown_modes)}"
                )
        if not reasoning_mode_ids:
            raise ValueError("at least one reasoning mode must be declared")
        if len(set(reasoning_mode_ids)) != len(reasoning_mode_ids):
            raise ValueError("reasoning mode ids must be unique")
        if self.execution.mode == "cascade":
            if len(self.execution.stages) < 2:
                raise ValueError("cascade execution requires at least two stages")
            stage_ids = [stage.id for stage in self.execution.stages]
            if len(set(stage_ids)) != len(stage_ids):
                raise ValueError("cascade stage ids must be unique")
            configured_models: set[str] = set()
            for index, stage in enumerate(self.execution.stages):
                if index == 0 and stage.apply_to != "all":
                    raise ValueError("the first cascade stage must apply_to all")
                if index > 0 and stage.apply_to != "unresolved":
                    raise ValueError("later cascade stages must apply_to unresolved")
                unknown = set(stage.models) - set(model_ids)
                if unknown:
                    raise ValueError(
                        f"unknown models in cascade stage {stage.id}: {sorted(unknown)}"
                    )
                unknown_prompts = set(stage.prompts) - set(prompt_ids)
                if unknown_prompts:
                    raise ValueError(
                        f"unknown prompts in cascade stage {stage.id}: {sorted(unknown_prompts)}"
                    )
                if len(set(stage.prompts)) != len(stage.prompts):
                    raise ValueError(f"duplicate prompts in cascade stage {stage.id}")
                overlap = configured_models.intersection(stage.models)
                if overlap:
                    raise ValueError(f"models occur in multiple cascade stages: {sorted(overlap)}")
                configured_models.update(stage.models)

            model_by_id = {model.id: model for model in self.models}
            cumulative_stage_models: list[str] = []
            for stage in self.execution.stages:
                cumulative_stage_models.extend(stage.models)
                resolution = stage.resolution or self.execution.resolution
                dimension = "applicability_presence"
                dimension_is_filtered = any(
                    not model.dimension_eligibility.applicability_presence for model in self.models
                )
                if not dimension_is_filtered:
                    continue
                eligible_count = sum(
                    model_by_id[model_id].dimension_eligibility.applicability_presence
                    for model_id in cumulative_stage_models
                )
                minimum_dimension_models = (
                    resolution.minimum_applicability_presence_models
                    or resolution.minimum_successful_models
                )
                if eligible_count < minimum_dimension_models:
                    raise ValueError(
                        f"cascade stage {stage.id} has only {eligible_count} cumulative "
                        f"{dimension} voters, below required minimum "
                        f"{minimum_dimension_models}"
                    )
        model_repetitions = {item.id: self.repetitions_for(item) for item in self.models}
        seen: set[tuple[str, str, str, int]] = set()
        for item in self.observations:
            if item.prompt_id not in prompt_ids:
                raise ValueError(f"unknown prompt_id in observation: {item.prompt_id}")
            if item.model_id not in model_ids:
                raise ValueError(f"unknown model_id in observation: {item.model_id}")
            configured_prompt_ids = {prompt.id for prompt in self.prompts_for_model(item.model_id)}
            if item.prompt_id not in configured_prompt_ids:
                raise ValueError(
                    f"prompt {item.prompt_id!r} is not configured for model {item.model_id!r}"
                )
            if item.reasoning_mode_id not in reasoning_mode_ids:
                raise ValueError(
                    f"unknown reasoning_mode_id in observation: {item.reasoning_mode_id}"
                )
            expected_repetitions = model_repetitions[item.model_id]
            if expected_repetitions == 0:
                raise ValueError(
                    f"observation repetition {item.repetition} exceeds "
                    f"configured repetitions 0 for {item.model_id}"
                )
            key = (
                item.prompt_id,
                item.model_id,
                item.reasoning_mode_id,
                item.repetition,
            )
            if key in seen:
                raise ValueError(f"duplicate matrix observation: {key}")
            seen.add(key)
        return self

    @classmethod
    def load(cls, path: Path) -> QualificationMatrixManifest:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        manifest = cls.model_validate(payload)
        base = path.parent
        observations = tuple(
            item.model_copy(
                update={
                    "qualification_report": (
                        item.qualification_report
                        if item.qualification_report.is_absolute()
                        else base / item.qualification_report
                    ),
                    "run_directory": (
                        None
                        if item.run_directory is None
                        else item.run_directory
                        if item.run_directory.is_absolute()
                        else base / item.run_directory
                    ),
                }
            )
            for item in manifest.observations
        )
        review_imports = tuple(
            item.model_copy(
                update={
                    "run_directory": (
                        item.run_directory
                        if item.run_directory.is_absolute()
                        else base / item.run_directory
                    ),
                    "review_directory": (
                        item.review_directory
                        if item.review_directory.is_absolute()
                        else base / item.review_directory
                    ),
                    "local_corpus_root": (
                        item.local_corpus_root
                        if item.local_corpus_root.is_absolute()
                        else base / item.local_corpus_root
                    ),
                }
            )
            for item in manifest.review_imports
        )
        consensus = manifest.consensus.model_copy(
            update={
                "output_directory": (
                    manifest.consensus.output_directory
                    if manifest.consensus.output_directory.is_absolute()
                    else base / manifest.consensus.output_directory
                )
            }
        )
        return manifest.model_copy(
            update={
                "observations": observations,
                "review_imports": review_imports,
                "consensus": consensus,
            }
        )


class CandidateQualification(BaseModel):
    """Aggregated result for one model/prompt candidate."""

    model_config = ConfigDict(frozen=True)

    prompt_id: str
    model_id: str
    provider: str
    reasoning_mode_id: str
    reasoning_optional: bool
    expected_repetitions: int
    completed_repetitions: int
    status: str
    qualification_eligible: bool
    mean_gold_f1: float | None
    min_gold_f1: float | None
    gold_f1_stddev: float | None
    mean_gold_coverage: float | None
    mean_silver_f1: float
    mean_structure_f1: float
    mean_prediction_success_rate: float
    mean_json_validity_rate: float
    mean_truncation_rate: float
    mean_duration_seconds: float | None = None
    performance_measurement_source: str = "legacy"
    fresh_prediction_count: int | None = None
    cached_prediction_count: int = 0
    reused_prediction_count: int = 0
    peak_memory_gb: float | None = None
    pareto_optimal: bool = False
    passed: bool
    regressions: tuple[str, ...] = ()
    failure_categories: dict[str, int] = {}
    top_failure_messages: tuple[str, ...] = ()


class QualificationMatrixReport(BaseModel):
    """Machine-readable comparison and acceptance result."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    matrix_id: str
    corpus_id: str
    generated_at: datetime
    passed: bool
    ranking: tuple[str, ...]
    pareto_front: tuple[str, ...]
    candidates: tuple[CandidateQualification, ...]
    diagnostics: tuple[str, ...] = ()


class ModelPromptQualificationService:
    """Aggregate repeated qualification reports and enforce regression gates."""

    def evaluate(
        self,
        manifest: QualificationMatrixManifest,
        output_directory: Path,
    ) -> tuple[QualificationMatrixReport, Path, Path]:
        grouped: dict[
            tuple[str, str, str],
            list[tuple[MatrixObservation, AnnotationQualificationReport]],
        ] = {}
        diagnostics: list[str] = []
        for observation in manifest.observations:
            report = AnnotationQualificationReport.model_validate_json(
                observation.qualification_report.read_text(encoding="utf-8")
            )
            if report.corpus_id != manifest.corpus_id:
                raise ValueError(
                    f"corpus mismatch in {observation.qualification_report}: "
                    f"{report.corpus_id} != {manifest.corpus_id}"
                )
            grouped.setdefault(
                (
                    observation.prompt_id,
                    observation.model_id,
                    observation.reasoning_mode_id,
                ),
                [],
            ).append((observation, report))

        model_map = {item.id: item for item in manifest.models}
        raw_candidates: list[CandidateQualification] = []
        for model in manifest.models:
            if manifest.repetitions_for(model) == 0:
                continue
            for prompt in manifest.prompts_for_model(model.id):
                for reasoning_mode in manifest.reasoning_modes:
                    entries = sorted(
                        grouped.get((prompt.id, model.id, reasoning_mode.id), []),
                        key=lambda item: item[0].repetition,
                    )
                    candidate = _aggregate_candidate(
                        prompt.id,
                        model,
                        reasoning_mode,
                        entries,
                        manifest.repetitions_for(model),
                        manifest.thresholds,
                    )
                    raw_candidates.append(candidate)
                    if reasoning_mode.id not in model.supported_reasoning_modes:
                        diagnostics.append(
                            f"unsupported reasoning mode for {prompt.id} / {model.id} / "
                            f"{reasoning_mode.id}"
                        )
                    elif not entries:
                        diagnostics.append(
                            f"missing all runs for {prompt.id} / {model.id} / {reasoning_mode.id}"
                        )

        from standards_atlas.application.semantic_qualification.ranking import (
            apply_baseline,
            candidate_key,
            pareto_front,
            rank_candidates,
        )

        candidates = apply_baseline(raw_candidates, manifest.thresholds)
        pareto_keys = pareto_front(candidates)
        candidates = tuple(
            item.model_copy(update={"pareto_optimal": candidate_key(item) in pareto_keys})
            for item in candidates
        )
        ranking = rank_candidates(candidates)
        report = QualificationMatrixReport(
            matrix_id=manifest.matrix_id,
            corpus_id=manifest.corpus_id,
            generated_at=datetime.now(UTC),
            passed=all(
                item.passed or item.reasoning_optional or item.status == "unsupported"
                for item in candidates
            )
            and any(item.qualification_eligible for item in candidates),
            ranking=ranking,
            pareto_front=tuple(key for key in ranking if key in pareto_keys),
            candidates=candidates,
            diagnostics=tuple(diagnostics),
        )
        output_directory.mkdir(parents=True, exist_ok=True)
        json_path = output_directory / "qualification-matrix.json"
        markdown_path = output_directory / "qualification-matrix.md"
        json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(
            render_qualification_matrix_markdown(report, model_map), encoding="utf-8"
        )
        return report, json_path, markdown_path


def _aggregate_candidate(
    prompt_id: str,
    model: ModelCandidate,
    reasoning_mode: ReasoningMode,
    entries: list[tuple[MatrixObservation, AnnotationQualificationReport]],
    expected_repetitions: int,
    thresholds: RegressionThresholds,
) -> CandidateQualification:
    """Compatibility wrapper for candidate aggregation."""
    from standards_atlas.application.semantic_qualification.aggregation import (
        aggregate_candidate,
    )

    return aggregate_candidate(
        prompt_id,
        model,
        reasoning_mode,
        entries,
        expected_repetitions,
        thresholds,
    )


def _empty_candidate(
    prompt_id: str,
    model: ModelCandidate,
    reasoning_mode: ReasoningMode,
    expected_repetitions: int,
    *,
    status: str,
) -> CandidateQualification:
    """Compatibility wrapper for empty candidate construction."""
    from standards_atlas.application.semantic_qualification.aggregation import (
        empty_candidate,
    )

    return empty_candidate(
        prompt_id,
        model,
        reasoning_mode,
        expected_repetitions,
        status=status,
    )


def _baseline(
    candidates: list[CandidateQualification], thresholds: RegressionThresholds
) -> CandidateQualification | None:
    """Compatibility wrapper for baseline selection."""
    from standards_atlas.application.semantic_qualification.ranking import find_baseline

    return find_baseline(candidates, thresholds)


def _apply_baseline_threshold(
    candidate: CandidateQualification,
    baseline: CandidateQualification | None,
    thresholds: RegressionThresholds,
) -> CandidateQualification:
    """Compatibility wrapper for baseline threshold application."""
    from standards_atlas.application.semantic_qualification.ranking import (
        apply_baseline_threshold,
    )

    return apply_baseline_threshold(candidate, baseline, thresholds)


def _candidate_key(candidate: CandidateQualification) -> str:
    """Compatibility wrapper for candidate key generation."""
    from standards_atlas.application.semantic_qualification.ranking import candidate_key

    return candidate_key(candidate)


def _pareto_front(candidates: tuple[CandidateQualification, ...]) -> set[str]:
    """Compatibility wrapper for Pareto-front calculation."""
    from standards_atlas.application.semantic_qualification.ranking import pareto_front

    return pareto_front(candidates)


def _dominates(left: CandidateQualification, right: CandidateQualification) -> bool:
    """Compatibility wrapper for pairwise dominance checks."""
    from standards_atlas.application.semantic_qualification.ranking import dominates

    return dominates(left, right)


def _markdown(
    report: QualificationMatrixReport,
    models: dict[str, ModelCandidate],
) -> str:
    """Compatibility wrapper for the extracted Markdown renderer."""
    return render_qualification_matrix_markdown(report, models)
