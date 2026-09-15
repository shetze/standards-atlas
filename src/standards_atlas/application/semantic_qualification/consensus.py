"""Applicability-presence consensus for semantic qualification matrices."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from statistics import median
from typing import Any, ClassVar, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.evaluation.repository import EvaluationDatasetRepository
from standards_atlas.application.schema import (
    require_current_payload,
    require_current_schema,
    require_supported_schema,
)
from standards_atlas.application.schema.model import SchemaBoundModel
from standards_atlas.application.semantic_qualification.annotations import (
    ClauseEvaluationAnnotation,
)


class ConsensusCategory(StrEnum):
    UNANIMOUS = "unanimous"
    STRONG = "strong_consensus"
    MAJORITY = "majority_consensus"
    DISPUTED = "disputed"
    INSUFFICIENT = "insufficient_evidence"


class OverallConsensusStatus(StrEnum):
    RESOLVED = "resolved"
    PARTIAL = "partially_resolved"
    REVIEW_REQUIRED = "review_required"


class ModelVote(BaseModel):
    """One stable applicability-presence vote contributed by a model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    applicability_present: bool
    applicability_presence_eligible: bool = True
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: str | None = None
    repetitions: int = Field(ge=1)
    stability: float = Field(ge=0.0, le=1.0)
    role: str = Field(default="voter", pattern="^(voter|adjudicator)$")


class ClauseConsensus(BaseModel):
    """Resolved applicability-presence decision for one source clause."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clause_id: str
    document_key: str
    reference: str | None = None
    heading: str | None = None
    clause_text: str | None = None
    category: ConsensusCategory
    applicability_category: ConsensusCategory
    overall_status: OverallConsensusStatus = OverallConsensusStatus.REVIEW_REQUIRED
    applicability_present: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    applicability_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    applicability_presence_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    applicability_decision_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    applicability_presence_unanimous: bool = True
    applicability_unanimous: bool = True
    applicability_participating_models: int = Field(default=0, ge=0)
    participating_models: int = Field(default=0, ge=0)
    votes: tuple[ModelVote, ...] = ()
    applicability_support: dict[str, float] = Field(default_factory=dict)
    structural_prior: dict[str, Any] = Field(default_factory=dict)
    scope_context: bool = False
    adjudicated: bool = False
    requires_review: bool = True
    review_reasons: tuple[str, ...] = ()
    resolution_sources: dict[str, str] = Field(default_factory=dict)


class ConsensusReport(SchemaBoundModel):
    """Applicability-presence consensus report."""

    SCHEMA_FAMILY: ClassVar[str] = "qualification-consensus"
    model_config = ConfigDict(frozen=True, revalidate_instances="always", extra="forbid")

    schema_version: Literal[1] = 1
    matrix_id: str
    corpus_id: str
    prompt_id: str
    reasoning_mode_id: str
    prompt_selection: dict[str, str] = Field(default_factory=dict)
    generated_at: datetime
    model_count: int = Field(ge=0)
    minimum_participating_models: int = Field(default=0, ge=0)
    median_participating_models: float = Field(default=0.0, ge=0.0)
    maximum_participating_models: int = Field(default=0, ge=0)
    participation_distribution: dict[str, int] = Field(default_factory=dict)
    review_policy: dict[str, Any] = Field(default_factory=dict)
    clause_count: int = Field(ge=0)
    categories: dict[str, int]
    review_count: int = Field(ge=0)
    dimension_categories: dict[str, dict[str, int]] = Field(default_factory=dict)
    overall_statuses: dict[str, int] = Field(default_factory=dict)
    resolution_sources: dict[str, int] = Field(default_factory=dict)
    clauses: tuple[ClauseConsensus, ...]


class ModelConsensusService:
    """Build model votes and resolve the applicability-presence dimension."""

    def evaluate(
        self,
        *,
        matrix_id: str,
        corpus_id: str,
        prompt_id: str,
        reasoning_mode_id: str,
        observations: tuple[object, ...],
        output_directory: Path,
        corpus_root: Path | None = None,
        min_models: int = 3,
        strong_threshold: float = 0.8,
        majority_threshold: float = 0.6,
        prompt_selection: dict[str, str] | None = None,
        review_policy: dict[str, Any] | None = None,
        adjudication: dict[str, Any] | None = None,
        example_ids: tuple[str, ...] | None = None,
        resolution_overrides: dict[str, dict[str, dict[str, Any]]] | None = None,
        model_dimension_eligibility: dict[str, dict[str, bool]] | None = None,
        min_applicability_presence_models: int | None = None,
    ) -> tuple[ConsensusReport, Path, Path, Path]:
        selected_prompt = (prompt_selection or {}).get("applicability") or prompt_id
        selected = tuple(
            item
            for item in observations
            if item.prompt_id == selected_prompt
            and item.reasoning_mode_id == reasoning_mode_id
            and getattr(item, "run_directory", None) is not None
        )
        if not selected:
            raise ValueError(
                "no proposal runs available for applicability prompt="
                f"{selected_prompt!r}, reasoning={reasoning_mode_id!r}"
            )

        predictions: dict[str, dict[str, list[ClauseEvaluationAnnotation]]] = defaultdict(
            lambda: defaultdict(list)
        )
        included_example_ids = set(example_ids or ())
        clause_contexts = _load_clause_contexts(selected, corpus_root)
        if included_example_ids:
            clause_contexts = {
                clause_id: context
                for clause_id, context in clause_contexts.items()
                if clause_id in included_example_ids
            }
        for observation in selected:
            run_directory = Path(observation.run_directory)
            for evaluation_path in sorted(run_directory.glob("*/evaluation.yaml")):
                payload = yaml.safe_load(evaluation_path.read_text(encoding="utf-8")) or {}
                require_supported_schema("semantic-evaluation", payload.get("schema_version"))
                annotation = ClauseEvaluationAnnotation.model_validate(
                    payload["annotation_candidate"]
                )
                if included_example_ids and annotation.clause.clause_id not in included_example_ids:
                    continue
                predictions[annotation.clause.clause_id][str(observation.model_id)].append(
                    annotation
                )

        policy = _review_policy(review_policy)
        adjudicator_cfg = adjudication or {}
        adjudicator_id = (
            str(adjudicator_cfg.get("model_id"))
            if adjudicator_cfg.get("enabled") and adjudicator_cfg.get("model_id")
            else None
        )

        clauses: list[ClauseConsensus] = []
        for clause_id, model_predictions in sorted(predictions.items()):
            context = clause_contexts.get(clause_id, {})
            all_annotations = [a for annotations in model_predictions.values() for a in annotations]
            if not all_annotations:
                continue
            clause_reference = all_annotations[0].clause
            votes = tuple(
                _model_vote(model_id, annotations, role="voter").model_copy(
                    update={
                        "applicability_presence_eligible": bool(
                            (model_dimension_eligibility or {})
                            .get(model_id, {})
                            .get("applicability_presence", True)
                        )
                    }
                )
                for model_id, annotations in sorted(model_predictions.items())
                if model_id != adjudicator_id
            )
            adjudicator_vote = None
            if adjudicator_id and adjudicator_id in model_predictions:
                adjudicator_vote = _model_vote(
                    adjudicator_id, model_predictions[adjudicator_id], role="adjudicator"
                ).model_copy(
                    update={
                        "applicability_presence_eligible": bool(
                            (model_dimension_eligibility or {})
                            .get(adjudicator_id, {})
                            .get("applicability_presence", True)
                        )
                    }
                )

            # Applicability consensus is source-only. Structural context may frame
            # model requests, but it does not contribute an independent consensus vote.
            prior: dict[str, Any] = {}
            result = _resolve_clause(
                votes=votes,
                adjudicator_vote=adjudicator_vote,
                minimum_models=min_models,
                strong_threshold=strong_threshold,
                majority_threshold=majority_threshold,
                adjudicator_min_confidence=float(adjudicator_cfg.get("minimum_confidence", 0.70)),
                policy=policy,
                resolution_override=(resolution_overrides or {}).get(clause_id, {}),
                min_applicability_presence_models=min_applicability_presence_models,
            )
            clauses.append(
                ClauseConsensus(
                    clause_id=clause_id,
                    document_key=clause_reference.document_key,
                    reference=_optional_text(context.get("reference")),
                    heading=_optional_text(context.get("heading") or context.get("title")),
                    clause_text=_optional_text(context.get("text")),
                    votes=votes + ((adjudicator_vote,) if adjudicator_vote else ()),
                    structural_prior=prior,
                    scope_context=bool(prior.get("scope_context", False)),
                    **result,
                )
            )

        category_counts = Counter(item.category.value for item in clauses)
        participation_counts = [item.participating_models for item in clauses]
        participation_distribution = Counter(participation_counts)
        report = ConsensusReport(
            matrix_id=matrix_id,
            corpus_id=corpus_id,
            prompt_id=selected_prompt,
            reasoning_mode_id=reasoning_mode_id,
            prompt_selection={"applicability": selected_prompt},
            generated_at=datetime.now(UTC),
            model_count=len({vote.model_id for clause in clauses for vote in clause.votes}),
            minimum_participating_models=min(participation_counts, default=0),
            median_participating_models=(
                float(median(participation_counts)) if participation_counts else 0.0
            ),
            maximum_participating_models=max(participation_counts, default=0),
            participation_distribution={
                str(count): occurrences
                for count, occurrences in sorted(participation_distribution.items())
            },
            review_policy={**policy, "review_categories": sorted(policy["review_categories"])},
            clause_count=len(clauses),
            categories=dict(sorted(category_counts.items())),
            review_count=sum(item.requires_review for item in clauses),
            dimension_categories={
                "applicability": dict(
                    sorted(Counter(item.applicability_category.value for item in clauses).items())
                )
            },
            overall_statuses=dict(
                sorted(Counter(item.overall_status.value for item in clauses).items())
            ),
            resolution_sources=dict(
                sorted(
                    Counter(
                        f"applicability:{source}"
                        for item in clauses
                        for source in item.resolution_sources.values()
                    ).items()
                )
            ),
            clauses=tuple(clauses),
        )
        return _write_outputs(report, output_directory)


def _model_vote(
    model_id: str,
    annotations: list[ClauseEvaluationAnnotation],
    *,
    role: str,
) -> ModelVote:
    modal = _modal_annotations(annotations)
    if modal is None:
        raise ValueError(f"model {model_id!r} has no applicability annotations")
    annotation, repetitions, stability = modal
    proposal = annotation.proposal
    return ModelVote(
        model_id=model_id,
        applicability_present=proposal.applicability_present,
        confidence=proposal.confidence,
        evidence=proposal.rationale,
        repetitions=repetitions,
        stability=stability,
        role=role,
    )


def _modal_annotations(
    annotations: list[ClauseEvaluationAnnotation],
) -> tuple[ClauseEvaluationAnnotation, int, float] | None:
    if not annotations:
        return None
    keys = [item.proposal.applicability_present for item in annotations]
    key, count = Counter(keys).most_common(1)[0]
    annotation = annotations[keys.index(key)]
    return annotation, len(annotations), count / len(annotations)


def _resolve_clause(
    *,
    votes: tuple[ModelVote, ...],
    adjudicator_vote: ModelVote | None,
    minimum_models: int,
    strong_threshold: float,
    majority_threshold: float,
    adjudicator_min_confidence: float,
    policy: dict[str, Any],
    resolution_override: dict[str, dict[str, Any]] | None = None,
    min_applicability_presence_models: int | None = None,
) -> dict[str, Any]:
    policy = _review_policy(policy)
    eligible = tuple(vote for vote in votes if vote.applicability_presence_eligible)
    required_presence_models = min_applicability_presence_models or minimum_models
    support = (
        sum(vote.applicability_present for vote in eligible) / len(eligible) if eligible else 0.0
    )
    present = support >= majority_threshold
    decision_confidence = support if present else 1.0 - support
    unanimous = len({vote.applicability_present for vote in eligible}) <= 1 if eligible else False
    category = _category_for_confidence(
        decision_confidence,
        len(eligible),
        required_presence_models,
        strong_threshold,
        majority_threshold,
    )
    adjudicated = False
    source = "model_consensus"

    override = (resolution_override or {}).get("applicability")
    if override:
        present = bool(override.get("present", present))
        decision_confidence = float(override.get("confidence", decision_confidence))
        category = _category_for_confidence(
            decision_confidence,
            max(len(eligible), required_presence_models),
            required_presence_models,
            strong_threshold,
            majority_threshold,
        )
        source = str(override.get("source") or "cascade_override")
    elif (
        adjudicator_vote is not None
        and adjudicator_vote.applicability_presence_eligible
        and category in {ConsensusCategory.DISPUTED, ConsensusCategory.INSUFFICIENT}
        and (adjudicator_vote.confidence or 0.0) >= adjudicator_min_confidence
    ):
        present = adjudicator_vote.applicability_present
        decision_confidence = max(decision_confidence, adjudicator_vote.confidence or 0.0)
        category = _category_for_confidence(
            decision_confidence,
            max(len(eligible), required_presence_models),
            required_presence_models,
            strong_threshold,
            majority_threshold,
        )
        adjudicated = True
        source = "adjudicator"

    reasons = _review_reasons(
        category=category,
        confidence=decision_confidence,
        participating_models=len(eligible),
        policy=policy,
    )
    requires_review = bool(reasons)
    return {
        "category": category,
        "applicability_category": category,
        "overall_status": (
            OverallConsensusStatus.REVIEW_REQUIRED
            if requires_review
            else OverallConsensusStatus.RESOLVED
        ),
        "applicability_present": present,
        "confidence": decision_confidence,
        "applicability_confidence": decision_confidence,
        "applicability_presence_confidence": decision_confidence,
        "applicability_decision_confidence": decision_confidence,
        "applicability_presence_unanimous": unanimous,
        "applicability_unanimous": unanimous,
        "applicability_participating_models": len(eligible),
        "participating_models": len(votes),
        "applicability_support": {"present": support, "absent": 1.0 - support},
        "adjudicated": adjudicated,
        "requires_review": requires_review,
        "review_reasons": reasons,
        "resolution_sources": {"applicability": source},
    }


def _category_for_confidence(
    confidence: float,
    count: int,
    minimum_models: int,
    strong_threshold: float,
    majority_threshold: float,
) -> ConsensusCategory:
    if count < minimum_models:
        return ConsensusCategory.INSUFFICIENT
    if confidence >= 1.0:
        return ConsensusCategory.UNANIMOUS
    if confidence >= strong_threshold:
        return ConsensusCategory.STRONG
    if confidence >= majority_threshold:
        return ConsensusCategory.MAJORITY
    return ConsensusCategory.DISPUTED


def _review_policy(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = value or {}
    return {
        "review_categories": set(
            raw.get("review_categories", {"disputed", "insufficient_evidence"})
        ),
        "accept_majority_min_confidence": float(raw.get("accept_majority_min_confidence", 0.67)),
        "accept_majority_min_models": int(raw.get("accept_majority_min_models", 3)),
        "applicability_min_confidence": float(raw.get("applicability_min_confidence", 0.75)),
    }


def _review_reasons(
    *,
    category: ConsensusCategory,
    confidence: float,
    participating_models: int,
    policy: dict[str, Any],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if category.value in policy["review_categories"]:
        reasons.append(f"consensus category is {category.value}")
    if category is ConsensusCategory.MAJORITY and (
        confidence < policy["accept_majority_min_confidence"]
        or participating_models < policy["accept_majority_min_models"]
    ):
        reasons.append("majority consensus is below automatic-acceptance threshold")
    if confidence < policy["applicability_min_confidence"]:
        reasons.append("applicability confidence is below review threshold")
    return tuple(dict.fromkeys(reasons))


def _write_outputs(
    report: ConsensusReport, output_directory: Path
) -> tuple[ConsensusReport, Path, Path, Path]:
    report = ConsensusReport.model_validate(report)
    require_current_schema("qualification-consensus", report.schema_version)
    require_current_schema("golden-corpus-proposal", 1)
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "consensus-report.json"
    yaml_path = output_directory / "golden-corpus-proposal.yaml"
    review_path = output_directory / "consensus-review.md"
    payload = {
        "schema_version": 1,
        "kind": "applicability_presence_proposal",
        "matrix_id": report.matrix_id,
        "corpus_id": report.corpus_id,
        "prompt_selection": report.prompt_selection,
        "clauses": [
            {
                "clause_id": item.clause_id,
                "document_key": item.document_key,
                "reference": item.reference,
                "heading": item.heading,
                "applicability": {"present": item.applicability_present},
                "confidence": item.applicability_decision_confidence,
                "consensus_category": item.applicability_category.value,
                "overall_status": item.overall_status.value,
                "resolution_sources": item.resolution_sources,
                "adjudicated": item.adjudicated,
                "requires_review": item.requires_review,
                "review_reasons": list(item.review_reasons),
            }
            for item in report.clauses
        ],
    }
    require_current_payload("golden-corpus-proposal", payload)
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    yaml_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    review_path.write_text(_render_review(report), encoding="utf-8")
    return report, json_path, yaml_path, review_path


def _render_review(report: ConsensusReport) -> str:
    lines = [
        f"# Applicability consensus review — {report.matrix_id}",
        "",
        "Review only clauses that remain uncertain after the qualified presence cascade.",
        "",
    ]
    ordered = sorted(
        report.clauses,
        key=lambda item: (
            not item.requires_review,
            item.applicability_decision_confidence,
            item.document_key,
            item.reference or "",
            item.clause_id,
        ),
    )
    for item in ordered:
        readable = item.reference or item.clause_id
        heading = f"## {item.document_key}:{readable}"
        if item.heading:
            heading += f" — {item.heading}"
        lines.extend(
            [
                heading,
                "",
                f"- Applicability present: `{str(item.applicability_present).lower()}`",
                f"- Category: `{item.applicability_category.value}`",
                f"- Confidence: `{item.applicability_decision_confidence:.3f}`",
                f"- Participating models: `{item.applicability_participating_models}`",
                f"- Review required: `{str(item.requires_review).lower()}`",
            ]
        )
        if item.review_reasons:
            lines.append("- Reasons: " + "; ".join(item.review_reasons))
        if item.clause_text:
            lines.extend(["", "> " + item.clause_text.replace("\n", "\n> ")])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _load_clause_contexts(
    observations: tuple[object, ...], corpus_root: Path | None
) -> dict[str, dict[str, object]]:
    if corpus_root is None:
        return {}
    for observation in observations:
        run_directory = Path(observation.run_directory)
        evaluation_path = next(iter(sorted(run_directory.glob("*/evaluation.yaml"))), None)
        if evaluation_path is None:
            continue
        payload = yaml.safe_load(evaluation_path.read_text(encoding="utf-8")) or {}
        require_supported_schema("semantic-evaluation", payload.get("schema_version"))
        run = payload.get("run") or {}
        task = run.get("task")
        dataset_version = run.get("dataset_version")
        if not isinstance(task, str) or not isinstance(dataset_version, str):
            continue
        dataset = EvaluationDatasetRepository(corpus_root).load(task, dataset_version)
        contexts: dict[str, dict[str, object]] = {}
        for example in dataset.examples:
            content = dict(example.input.get("content", {}))
            context = dict(example.input.get("context", {}))
            contexts[example.id] = {**context, "text": content.get("text")}
        return contexts
    return {}


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
