"""Model and prompt qualification matrices for semantic annotation runs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from standards_atlas.application.semantic_qualification.qualification import (
    AnnotationQualificationReport,
)
from standards_atlas.application.semantic_qualification.reports.matrix import (
    render_qualification_matrix_markdown,
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


def resolve_prompt_version(
    prompt: PromptCandidate,
    *,
    resources: Path,
    task: str = "statement-function-classification",
) -> str:
    """Resolve a matrix prompt id to an installed prompt resource version."""
    candidates = [prompt.prompt_version, _PROMPT_VERSION_ALIASES.get(prompt.id), prompt.id]
    checked: list[str] = []
    for candidate in candidates:
        if not candidate or candidate in checked:
            continue
        checked.append(candidate)
        definition = resources / "prompts" / task / candidate / "prompt.json"
        if definition.is_file():
            return candidate
    available_root = resources / "prompts" / task
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


class CascadeStage(BaseModel):
    """One ordered model and prompt stage in cascade execution."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    models: tuple[str, ...] = Field(min_length=1)
    prompts: tuple[str, ...] = ()
    apply_to: str = Field(default="all", pattern="^(all|unresolved)$")


class CascadeResolutionConfig(BaseModel):
    """Rules used to decide whether a clause needs escalation."""

    model_config = ConfigDict(frozen=True)

    minimum_successful_models: int = Field(default=3, ge=1)
    accepted_categories: tuple[str, ...] = (
        "unanimous",
        "strong_consensus",
        "majority_consensus",
    )
    minimum_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    escalate_on_applicability_disagreement: bool = True
    escalate_on_responsibility_disagreement: bool = True


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
    if resolution.escalate_on_applicability_disagreement and not clause.applicability_unanimous:
        reasons.append("applicability_disagreement")
    if resolution.escalate_on_responsibility_disagreement and not clause.responsibility_unanimous:
        reasons.append("responsibility_disagreement")
    return tuple(reasons)


class MatrixExecutionConfig(BaseModel):
    """Execution strategy shared by full and cascade qualification runs."""

    model_config = ConfigDict(frozen=True)

    mode: str = Field(default="full_matrix", pattern="^(full_matrix|cascade)$")
    stages: tuple[CascadeStage, ...] = ()
    resolution: CascadeResolutionConfig = CascadeResolutionConfig()


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
    local_corpus_root: Path = Path("local/evaluation/corpora")
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
    responsibility_min_confidence: float = Field(default=0.80, ge=0.0, le=1.0)
    require_responsibility_evidence: bool = True


class ConsensusPromptSelection(BaseModel):
    """Prompt family used for each semantic dimension."""

    model_config = ConfigDict(frozen=True)

    statement_function: str = "content-only"
    applicability: str = "content-only"
    responsibility: str = "content-only"


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
    output_directory: Path = Path("local/evaluation/consensus")


class QualificationMatrixManifest(BaseModel):
    """Versioned contract for Slice 5.4.6 qualification."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    matrix_id: str = Field(min_length=1)
    corpus_id: str = Field(min_length=1)
    task_version: str = Field(default="1.0.0", min_length=1)
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

    def repetitions_for(self, model: ModelCandidate) -> int:
        """Return the model-specific repetition count or the global default."""
        return model.repetitions if model.repetitions is not None else self.repetitions

    def prompts_for_stage(self, stage: CascadeStage) -> tuple[PromptCandidate, ...]:
        """Return the prompts selected for a cascade stage."""
        if not stage.prompts:
            return self.prompts
        selected = set(stage.prompts)
        return tuple(prompt for prompt in self.prompts if prompt.id in selected)

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
        if len(self.prompts) != 4:
            raise ValueError("qualification matrix must declare exactly four prompt variants")
        prompt_ids = [item.id for item in self.prompts]
        model_ids = [item.id for item in self.models]
        reasoning_mode_ids = [item.id for item in self.reasoning_modes]
        if len(set(prompt_ids)) != len(prompt_ids):
            raise ValueError("prompt candidate ids must be unique")
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("model candidate ids must be unique")
        adjudicator = self.consensus.adjudication
        if adjudicator.enabled and adjudicator.model_id not in model_ids:
            raise ValueError(f"unknown consensus adjudicator model: {adjudicator.model_id!r}")
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
