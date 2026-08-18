"""Normalization-aware model consensus for semantic qualification matrices."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from statistics import median
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.evaluation.repository import EvaluationDatasetRepository
from standards_atlas.application.semantic_qualification.annotations import (
    ClauseEvaluationAnnotation,
)
from standards_atlas.application.semantic_qualification.structural_evidence import (
    derive_structural_evidence,
)
from standards_atlas.domain.model import (
    ApplicabilityFunction,
    KnowledgeKind,
    ResponsibilityFunction,
    StatementFunction,
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
    """One stable, dimension-aware vote contributed by a model."""

    model_config = ConfigDict(frozen=True)

    model_id: str
    primary_function: StatementFunction | None = None
    secondary_functions: tuple[StatementFunction, ...] = ()
    primary_knowledge_kind: KnowledgeKind | None = None
    secondary_knowledge_kinds: tuple[KnowledgeKind, ...] = ()
    applicability_present: bool = False
    applicability_function: ApplicabilityFunction | None = None
    responsibility_present: bool = False
    responsibility_function: ResponsibilityFunction | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: str | None = None
    repetitions: int = Field(ge=1)
    stability: float = Field(ge=0.0, le=1.0)
    role: str = Field(default="voter", pattern="^(voter|adjudicator)$")

    @property
    def statement_functions(self) -> tuple[StatementFunction, ...]:
        if self.primary_function is None:
            return self.secondary_functions
        return (self.primary_function, *self.secondary_functions)

    @property
    def knowledge_kinds(self) -> tuple[KnowledgeKind, ...]:
        if self.primary_knowledge_kind is None:
            return self.secondary_knowledge_kinds
        return (self.primary_knowledge_kind, *self.secondary_knowledge_kinds)

    @property
    def applicability_functions(self) -> tuple[ApplicabilityFunction, ...]:
        if not self.applicability_present or self.applicability_function is None:
            return ()
        return (self.applicability_function,)

    @property
    def responsibility_functions(self) -> tuple[ResponsibilityFunction, ...]:
        if not self.responsibility_present or self.responsibility_function is None:
            return ()
        return (self.responsibility_function,)


class ClauseConsensus(BaseModel):
    model_config = ConfigDict(frozen=True)

    clause_id: str
    document_key: str
    reference: str | None = None
    title: str | None = None
    clause_text: str | None = None
    category: ConsensusCategory
    statement_function_category: ConsensusCategory = ConsensusCategory.INSUFFICIENT
    knowledge_kind_category: ConsensusCategory = ConsensusCategory.INSUFFICIENT
    applicability_category: ConsensusCategory = ConsensusCategory.INSUFFICIENT
    responsibility_category: ConsensusCategory = ConsensusCategory.INSUFFICIENT
    overall_status: OverallConsensusStatus = OverallConsensusStatus.REVIEW_REQUIRED
    primary_function: StatementFunction | None = None
    proposed_functions: tuple[StatementFunction, ...] = ()
    primary_knowledge_kind: KnowledgeKind | None = None
    proposed_knowledge_kinds: tuple[KnowledgeKind, ...] = ()
    applicability_present: bool = False
    proposed_applicability_functions: tuple[ApplicabilityFunction, ...] = ()
    responsibility_present: bool = False
    proposed_responsibility_functions: tuple[ResponsibilityFunction, ...] = ()
    # Overall confidence follows the primary statement-function dimension.
    # Keep this field for report compatibility while exposing every semantic
    # dimension explicitly below.
    confidence: float = Field(ge=0.0, le=1.0)
    statement_function_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    knowledge_kind_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    applicability_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    responsibility_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    statement_function_decision_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    knowledge_kind_decision_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    applicability_decision_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    responsibility_decision_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    applicability_unanimous: bool = True
    responsibility_unanimous: bool = True
    applicability_structural_conflict: bool = False
    participating_models: int = Field(ge=0)
    votes: tuple[ModelVote, ...] = ()
    label_support: dict[str, float] = Field(default_factory=dict)
    knowledge_kind_support: dict[str, float] = Field(default_factory=dict)
    applicability_support: dict[str, float] = Field(default_factory=dict)
    responsibility_support: dict[str, float] = Field(default_factory=dict)
    structural_prior: dict[str, Any] = Field(default_factory=dict)
    scope_context: bool = False
    adjudicated: bool = False
    requires_review: bool = True
    review_reasons: tuple[str, ...] = ()
    resolution_sources: dict[str, str] = Field(default_factory=dict)


class ConsensusReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "2.1"
    matrix_id: str
    corpus_id: str
    prompt_id: str
    reasoning_mode_id: str
    prompt_selection: dict[str, str] = Field(default_factory=dict)
    generated_at: datetime
    model_count: int
    minimum_participating_models: int = Field(default=0, ge=0)
    median_participating_models: float = Field(default=0.0, ge=0.0)
    maximum_participating_models: int = Field(default=0, ge=0)
    participation_distribution: dict[str, int] = Field(default_factory=dict)
    review_policy: dict[str, Any] = Field(default_factory=dict)
    clause_count: int
    categories: dict[str, int]
    review_count: int
    dimension_categories: dict[str, dict[str, int]] = Field(default_factory=dict)
    overall_statuses: dict[str, int] = Field(default_factory=dict)
    resolution_sources: dict[str, int] = Field(default_factory=dict)
    clauses: tuple[ClauseConsensus, ...]


class ModelConsensusService:
    """Build dimension-aware votes and apply priors, evidence gates and adjudication."""

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
        label_threshold: float = 0.6,
        prompt_selection: dict[str, str] | None = None,
        review_policy: dict[str, Any] | None = None,
        adjudication: dict[str, Any] | None = None,
        structural_priors: dict[str, Any] | None = None,
        example_ids: tuple[str, ...] | None = None,
        resolution_overrides: dict[str, dict[str, dict[str, Any]]] | None = None,
    ) -> tuple[ConsensusReport, Path, Path, Path]:
        prompts = {
            "statement_function": prompt_id,
            "knowledge_kind": prompt_id,
            "applicability": prompt_id,
            "responsibility": prompt_id,
            **(prompt_selection or {}),
        }
        selected_prompt_ids = set(prompts.values())
        selected = tuple(
            item
            for item in observations
            if item.prompt_id in selected_prompt_ids
            and item.reasoning_mode_id == reasoning_mode_id
            and getattr(item, "run_directory", None) is not None
        )
        if not selected:
            raise ValueError(
                "no proposal runs available for consensus prompts="
                f"{sorted(selected_prompt_ids)!r}, reasoning={reasoning_mode_id!r}"
            )

        predictions: dict[str, dict[str, dict[str, list[ClauseEvaluationAnnotation]]]] = (
            defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
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
                annotation = ClauseEvaluationAnnotation.model_validate(
                    payload["annotation_candidate"]
                )
                if included_example_ids and annotation.clause.clause_id not in included_example_ids:
                    continue
                predictions[annotation.clause.clause_id][str(observation.model_id)][
                    str(observation.prompt_id)
                ].append(annotation)

        policy = _review_policy(review_policy)
        adjudicator_cfg = adjudication or {}
        adjudicator_id = (
            str(adjudicator_cfg.get("model_id"))
            if adjudicator_cfg.get("enabled") and adjudicator_cfg.get("model_id")
            else None
        )
        prior_cfg = structural_priors or {"enabled": True, "confidence": 0.95}

        clauses: list[ClauseConsensus] = []
        for clause_id, model_predictions in sorted(predictions.items()):
            context = clause_contexts.get(clause_id, {})
            all_annotations = [
                annotation
                for prompt_predictions in model_predictions.values()
                for annotations in prompt_predictions.values()
                for annotation in annotations
            ]
            clause_reference = all_annotations[0].clause
            votes = [
                _model_vote(model_id, by_prompt, prompts, role="voter")
                for model_id, by_prompt in sorted(model_predictions.items())
                if model_id != adjudicator_id
            ]
            adjudicator_vote = None
            if adjudicator_id and adjudicator_id in model_predictions:
                adjudicator_vote = _model_vote(
                    adjudicator_id,
                    model_predictions[adjudicator_id],
                    prompts,
                    role="adjudicator",
                )

            prior = (
                derive_structural_evidence(
                    context, confidence=float(prior_cfg.get("confidence", 0.95))
                ).as_dict()
                if prior_cfg.get("enabled", True)
                else {}
            )
            result = _resolve_clause(
                votes=tuple(votes),
                adjudicator_vote=adjudicator_vote,
                structural_prior=prior,
                minimum_models=min_models,
                strong_threshold=strong_threshold,
                majority_threshold=majority_threshold,
                label_threshold=label_threshold,
                adjudicator_min_confidence=float(adjudicator_cfg.get("minimum_confidence", 0.70)),
                policy=policy,
                resolution_override=(resolution_overrides or {}).get(clause_id, {}),
                scope_context=bool(prior.get("scope_context", False)),
            )
            clauses.append(
                ClauseConsensus(
                    clause_id=clause_id,
                    document_key=clause_reference.document_key,
                    reference=_optional_text(context.get("reference")),
                    title=_optional_text(context.get("title")),
                    clause_text=_optional_text(context.get("text")),
                    votes=tuple(votes) + ((adjudicator_vote,) if adjudicator_vote else ()),
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
            prompt_id=prompt_id,
            reasoning_mode_id=reasoning_mode_id,
            prompt_selection=prompts,
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
            review_policy=policy,
            clause_count=len(clauses),
            categories=dict(sorted(category_counts.items())),
            review_count=sum(item.requires_review for item in clauses),
            dimension_categories={
                dimension: dict(
                    sorted(Counter(getattr(item, field).value for item in clauses).items())
                )
                for dimension, field in (
                    ("statement_function", "statement_function_category"),
                    ("knowledge_kind", "knowledge_kind_category"),
                    ("applicability", "applicability_category"),
                    ("responsibility", "responsibility_category"),
                )
            },
            overall_statuses=dict(
                sorted(Counter(item.overall_status.value for item in clauses).items())
            ),
            resolution_sources=dict(
                sorted(
                    Counter(
                        f"{dimension}:{source}"
                        for item in clauses
                        for dimension, source in item.resolution_sources.items()
                    ).items()
                )
            ),
            clauses=tuple(clauses),
        )
        return _write_outputs(report, output_directory)


def _model_vote(
    model_id: str,
    by_prompt: dict[str, list[ClauseEvaluationAnnotation]],
    prompts: dict[str, str],
    *,
    role: str,
) -> ModelVote:
    statement = _modal_annotations(by_prompt.get(prompts["statement_function"], []))
    knowledge = _modal_annotations(by_prompt.get(prompts["knowledge_kind"], []))
    applicability = _modal_annotations(by_prompt.get(prompts["applicability"], []))
    responsibility = _modal_annotations(by_prompt.get(prompts["responsibility"], []))
    available = [
        item for item in (statement, knowledge, applicability, responsibility) if item is not None
    ]
    if not available:
        raise ValueError(f"model {model_id!r} has no annotations for selected prompts")
    statement = statement or available[0]
    knowledge = knowledge or available[0]
    applicability = applicability or available[0]
    responsibility = responsibility or available[0]
    proposal = statement[0].proposal
    primary = proposal.primary_function
    if primary is None and proposal.statement_functions:
        primary = proposal.statement_functions[0]
    secondary = tuple(item for item in proposal.statement_functions if item != primary)
    knowledge_proposal = knowledge[0].proposal
    primary_knowledge = knowledge_proposal.primary_knowledge_kind
    if primary_knowledge is None and knowledge_proposal.knowledge_kinds:
        primary_knowledge = knowledge_proposal.knowledge_kinds[0]
    secondary_knowledge = tuple(
        item for item in knowledge_proposal.knowledge_kinds if item != primary_knowledge
    )
    app = applicability[0].proposal.primary_applicability_function
    if app is None and applicability[0].proposal.applicability_functions:
        app = applicability[0].proposal.applicability_functions[0]
    resp = responsibility[0].proposal.primary_responsibility_function
    if resp is None and responsibility[0].proposal.responsibility_functions:
        resp = responsibility[0].proposal.responsibility_functions[0]
    evidence = (
        " | ".join(
            value
            for value in (
                statement[0].proposal.rationale,
                knowledge[0].proposal.rationale,
                applicability[0].proposal.rationale,
                responsibility[0].proposal.rationale,
            )
            if value
        )
        or None
    )
    confidences = [
        item[0].proposal.confidence
        for item in (statement, knowledge, applicability, responsibility)
        if item[0].proposal.confidence is not None
    ]
    return ModelVote(
        model_id=model_id,
        primary_function=primary,
        secondary_functions=secondary,
        primary_knowledge_kind=primary_knowledge,
        secondary_knowledge_kinds=secondary_knowledge,
        applicability_present=app is not None,
        applicability_function=app,
        responsibility_present=resp is not None,
        responsibility_function=resp,
        confidence=min(confidences) if confidences else None,
        evidence=evidence,
        repetitions=max(item[1] for item in available),
        stability=min(item[2] for item in available),
        role=role,
    )


def _modal_annotations(
    annotations: list[ClauseEvaluationAnnotation],
) -> tuple[ClauseEvaluationAnnotation, int, float] | None:
    if not annotations:
        return None
    keys = [
        (
            item.proposal.primary_function,
            item.proposal.statement_functions,
            item.proposal.primary_knowledge_kind,
            item.proposal.knowledge_kinds,
            item.proposal.primary_applicability_function,
            item.proposal.applicability_functions,
            item.proposal.primary_responsibility_function,
            item.proposal.responsibility_functions,
        )
        for item in annotations
    ]
    key, count = Counter(keys).most_common(1)[0]
    annotation = annotations[keys.index(key)]
    return annotation, len(annotations), count / len(annotations)


def _resolve_clause(
    *,
    votes: tuple[ModelVote, ...],
    adjudicator_vote: ModelVote | None,
    structural_prior: dict[str, Any],
    minimum_models: int,
    strong_threshold: float,
    majority_threshold: float,
    label_threshold: float,
    adjudicator_min_confidence: float,
    policy: dict[str, Any],
    resolution_override: dict[str, dict[str, Any]] | None = None,
    scope_context: bool = False,
) -> dict[str, Any]:
    policy = _review_policy(policy)
    model_count = len(votes)
    primary_counts = Counter(vote.primary_function for vote in votes)
    primary, primary_count = primary_counts.most_common(1)[0] if primary_counts else (None, 0)
    primary_agreement = primary_count / model_count if model_count else 0.0

    prior_primary = structural_prior.get("primary_function")
    prior_confidence = float(structural_prior.get("confidence", 0.0))
    if prior_primary:
        prior_function = StatementFunction(prior_primary)
        if prior_function != primary:
            primary = prior_function
            primary_agreement = prior_confidence
        else:
            primary_agreement = max(primary_agreement, prior_confidence)

    adjudicated = False
    if (
        adjudicator_vote is not None
        and adjudicator_vote.primary_function is not None
        and primary_agreement < strong_threshold
        and (adjudicator_vote.confidence or 0.0) >= adjudicator_min_confidence
    ):
        primary = adjudicator_vote.primary_function
        primary_agreement = max(primary_agreement, adjudicator_vote.confidence or 0.0)
        adjudicated = True

    secondary_labels = sorted(
        {label for vote in votes for label in vote.secondary_functions},
        key=lambda item: item.value,
    )
    label_support = {
        label.value: sum(label in vote.secondary_functions for vote in votes) / model_count
        for label in secondary_labels
    }
    prior_functions = tuple(
        StatementFunction(value) for value in structural_prior.get("statement_functions", ())
    )
    proposed_functions = (() if primary is None else (primary,)) + tuple(
        label
        for label in dict.fromkeys((*prior_functions, *secondary_labels))
        if label != primary
        and (label in prior_functions or label_support.get(label.value, 0.0) >= label_threshold)
    )
    for label in prior_functions:
        label_support[label.value] = max(label_support.get(label.value, 0.0), prior_confidence)
    if primary is not None:
        label_support = {primary.value: primary_agreement, **label_support}

    knowledge_counts = Counter(vote.primary_knowledge_kind for vote in votes)
    primary_knowledge, knowledge_count = (
        knowledge_counts.most_common(1)[0] if knowledge_counts else (None, 0)
    )
    knowledge_agreement = knowledge_count / model_count if model_count else 0.0
    secondary_knowledge = sorted(
        {label for vote in votes for label in vote.secondary_knowledge_kinds},
        key=lambda item: item.value,
    )
    knowledge_kind_support = {
        label.value: sum(label in vote.secondary_knowledge_kinds for vote in votes) / model_count
        for label in secondary_knowledge
    }
    proposed_knowledge_kinds = (() if primary_knowledge is None else (primary_knowledge,)) + tuple(
        label
        for label in secondary_knowledge
        if label != primary_knowledge and knowledge_kind_support[label.value] >= label_threshold
    )
    if primary_knowledge is not None:
        knowledge_kind_support = {
            primary_knowledge.value: knowledge_agreement,
            **knowledge_kind_support,
        }

    app_present_support = (
        sum(vote.applicability_present for vote in votes) / model_count if model_count else 0.0
    )
    app_counts = Counter(
        vote.applicability_function for vote in votes if vote.applicability_present
    )
    app_label, app_count = app_counts.most_common(1)[0] if app_counts else (None, 0)
    app_label_support = app_count / model_count if model_count else 0.0
    prior_app = structural_prior.get("applicability_subtype")
    applicability_structural_conflict = bool(
        prior_app
        and app_label is not None
        and app_label.value != prior_app
        and app_label_support >= majority_threshold
        and prior_confidence >= majority_threshold
    )
    if prior_app and app_label_support < majority_threshold:
        app_label = ApplicabilityFunction(prior_app)
        app_present_support = max(app_present_support, prior_confidence)
        app_label_support = max(app_label_support, prior_confidence)
    app_accepted = app_present_support >= majority_threshold and app_label is not None

    valid_responsibility_votes = tuple(
        vote for vote in votes if _responsibility_evidence_is_valid(vote)
    )
    resp_present_support = len(valid_responsibility_votes) / model_count if model_count else 0.0
    resp_counts = Counter(vote.responsibility_function for vote in valid_responsibility_votes)
    resp_label, resp_count = resp_counts.most_common(1)[0] if resp_counts else (None, 0)
    resp_label_support = resp_count / model_count if model_count else 0.0
    resp_accepted = resp_present_support >= majority_threshold and resp_label is not None

    applicability_unanimous = _dimension_votes_are_unanimous(
        tuple(
            (
                vote.applicability_present,
                vote.applicability_function if vote.applicability_present else None,
            )
            for vote in votes
        )
    )
    responsibility_unanimous = _dimension_votes_are_unanimous(
        tuple(
            (
                vote.responsibility_present,
                vote.responsibility_function if vote.responsibility_present else None,
            )
            for vote in votes
        )
    )

    if model_count < minimum_models:
        category = ConsensusCategory.INSUFFICIENT
    elif primary_agreement >= 1.0:
        category = ConsensusCategory.UNANIMOUS
    elif primary_agreement >= strong_threshold:
        category = ConsensusCategory.STRONG
    elif primary_agreement >= majority_threshold or adjudicated:
        category = ConsensusCategory.MAJORITY
    else:
        category = ConsensusCategory.DISPUTED

    statement_function_confidence = primary_agreement
    knowledge_kind_confidence = knowledge_agreement if primary_knowledge is not None else 0.0
    applicability_decision_confidence = _dimension_decision_confidence(
        present=app_accepted,
        positive_confidence=app_label_support,
        support={"present": app_present_support},
    )
    responsibility_decision_confidence = _dimension_decision_confidence(
        present=resp_accepted,
        positive_confidence=resp_label_support,
        support={"present": resp_present_support},
    )
    applicability_confidence = app_label_support if app_label is not None else 0.0
    responsibility_confidence = resp_label_support if resp_label is not None else 0.0

    statement_category = category
    knowledge_category = _category_for_confidence(
        knowledge_kind_confidence, model_count, minimum_models, strong_threshold, majority_threshold
    )
    applicability_category = _category_for_confidence(
        applicability_decision_confidence,
        model_count,
        minimum_models,
        strong_threshold,
        majority_threshold,
    )
    responsibility_category = _category_for_confidence(
        responsibility_decision_confidence,
        model_count,
        minimum_models,
        strong_threshold,
        majority_threshold,
    )

    statement_function_decision_confidence = statement_function_confidence
    knowledge_kind_decision_confidence = knowledge_agreement
    resolution_sources: dict[str, str] = {}
    override = resolution_override or {}
    if "statement_function" in override:
        item = override["statement_function"]
        primary = StatementFunction(item["value"]) if item.get("value") else None
        statement_function_confidence = float(item["confidence"])
        statement_function_decision_confidence = float(item["confidence"])
        statement_category = ConsensusCategory(item["category"])
        category = statement_category
        resolution_sources["statement_function"] = str(item.get("source", "cascade"))
    if "knowledge_kind" in override:
        item = override["knowledge_kind"]
        primary_knowledge = KnowledgeKind(item["value"]) if item.get("value") else None
        knowledge_kind_decision_confidence = float(item["confidence"])
        knowledge_kind_confidence = (
            knowledge_kind_decision_confidence if primary_knowledge is not None else 0.0
        )
        knowledge_category = ConsensusCategory(item["category"])
        resolution_sources["knowledge_kind"] = str(item.get("source", "cascade"))
    if "applicability" in override:
        item = override["applicability"]
        app_label = ApplicabilityFunction(item["value"]) if item.get("value") else None
        app_accepted = bool(item.get("present", app_label is not None))
        applicability_decision_confidence = float(item["confidence"])
        applicability_confidence = (
            applicability_decision_confidence if app_accepted and app_label is not None else 0.0
        )
        applicability_category = ConsensusCategory(item["category"])
        resolution_sources["applicability"] = str(item.get("source", "cascade"))
    if "responsibility" in override:
        item = override["responsibility"]
        resp_label = ResponsibilityFunction(item["value"]) if item.get("value") else None
        resp_accepted = bool(item.get("present", resp_label is not None))
        responsibility_decision_confidence = float(item["confidence"])
        responsibility_confidence = (
            responsibility_decision_confidence if resp_accepted and resp_label is not None else 0.0
        )
        responsibility_category = ConsensusCategory(item["category"])
        resolution_sources["responsibility"] = str(item.get("source", "cascade"))

    proposed_functions = (() if primary is None else (primary,)) + tuple(
        value for value in proposed_functions if value != primary
    )
    proposed_knowledge_kinds = (() if primary_knowledge is None else (primary_knowledge,)) + tuple(
        value for value in proposed_knowledge_kinds if value != primary_knowledge
    )

    # Keep ``category`` as a compatibility field. In scope context applicability
    # is the governing semantic dimension; elsewhere statement function remains
    # the compatibility category. The per-dimension categories are authoritative.
    category = applicability_category if scope_context else statement_category
    confidence = (
        applicability_decision_confidence
        if scope_context
        else statement_function_decision_confidence
    )
    review_reasons = _review_reasons(
        category=category,
        statement_function_confidence=statement_function_confidence,
        model_count=model_count,
        applicability_present=app_accepted,
        applicability_confidence=applicability_confidence,
        responsibility_present=resp_accepted,
        responsibility_confidence=responsibility_confidence,
        applicability_structural_conflict=applicability_structural_conflict,
        policy=policy,
    )
    return {
        "category": category,
        "statement_function_category": statement_category,
        "knowledge_kind_category": knowledge_category,
        "applicability_category": applicability_category,
        "responsibility_category": responsibility_category,
        "overall_status": (
            OverallConsensusStatus.REVIEW_REQUIRED
            if review_reasons
            else (
                OverallConsensusStatus.PARTIAL
                if any(
                    item in {ConsensusCategory.DISPUTED, ConsensusCategory.INSUFFICIENT}
                    for item in (
                        statement_category,
                        knowledge_category,
                        applicability_category,
                        responsibility_category,
                    )
                )
                else OverallConsensusStatus.RESOLVED
            )
        ),
        "primary_function": primary,
        "proposed_functions": proposed_functions,
        "primary_knowledge_kind": primary_knowledge,
        "proposed_knowledge_kinds": proposed_knowledge_kinds,
        "applicability_present": app_accepted,
        "proposed_applicability_functions": ((app_label,) if app_accepted else ()),
        "responsibility_present": resp_accepted,
        "proposed_responsibility_functions": ((resp_label,) if resp_accepted else ()),
        "confidence": confidence,
        "statement_function_confidence": statement_function_confidence,
        "knowledge_kind_confidence": knowledge_kind_confidence,
        "applicability_confidence": applicability_confidence,
        "responsibility_confidence": responsibility_confidence,
        "statement_function_decision_confidence": statement_function_decision_confidence,
        "knowledge_kind_decision_confidence": knowledge_kind_decision_confidence,
        "applicability_decision_confidence": applicability_decision_confidence,
        "responsibility_decision_confidence": responsibility_decision_confidence,
        "applicability_unanimous": applicability_unanimous,
        "responsibility_unanimous": responsibility_unanimous,
        "applicability_structural_conflict": applicability_structural_conflict,
        "participating_models": model_count,
        "label_support": label_support,
        "knowledge_kind_support": knowledge_kind_support,
        "applicability_support": {
            "present": app_present_support,
            **({app_label.value: app_label_support} if app_label else {}),
        },
        "responsibility_support": {
            "present": resp_present_support,
            **({resp_label.value: resp_label_support} if resp_label else {}),
        },
        "adjudicated": adjudicated,
        "requires_review": bool(review_reasons),
        "review_reasons": tuple(review_reasons),
        "resolution_sources": resolution_sources,
    }


def _dimension_decision_confidence(
    *, present: bool, positive_confidence: float, support: dict[str, float]
) -> float:
    if present:
        return positive_confidence
    return max(0.0, 1.0 - float(support.get("present", 0.0)))


def _category_for_confidence(
    confidence: float,
    model_count: int,
    minimum_models: int,
    strong_threshold: float,
    majority_threshold: float,
) -> ConsensusCategory:
    if model_count < minimum_models:
        return ConsensusCategory.INSUFFICIENT
    if confidence >= 1.0:
        return ConsensusCategory.UNANIMOUS
    if confidence >= strong_threshold:
        return ConsensusCategory.STRONG
    if confidence >= majority_threshold:
        return ConsensusCategory.MAJORITY
    return ConsensusCategory.DISPUTED


def _dimension_votes_are_unanimous(votes: tuple[tuple[object, ...], ...]) -> bool:
    """Return whether every participating model made the same dimension decision.

    ``none`` is a real model decision for disagreement detection. This is
    intentionally different from positive-label confidence, where absence of a
    label contributes no positive evidence.
    """
    return len(set(votes)) <= 1


def _review_policy(payload: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "review_categories": {"disputed", "insufficient_evidence"},
        "accept_majority_min_confidence": 0.67,
        "accept_majority_min_models": 3,
        "applicability_min_confidence": 0.75,
        "responsibility_min_confidence": 0.80,
        "require_responsibility_evidence": True,
        **(payload or {}),
    }


def _review_reasons(
    *,
    category: ConsensusCategory,
    statement_function_confidence: float,
    model_count: int,
    applicability_present: bool,
    applicability_confidence: float,
    responsibility_present: bool,
    responsibility_confidence: float,
    applicability_structural_conflict: bool = False,
    policy: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    categories = {str(item) for item in policy["review_categories"]}
    if category.value in categories:
        reasons.append(f"consensus category is {category.value}")
    if category is ConsensusCategory.MAJORITY and (
        statement_function_confidence < float(policy["accept_majority_min_confidence"])
        or model_count < int(policy["accept_majority_min_models"])
    ):
        reasons.append("majority consensus does not meet automatic-acceptance policy")
    if applicability_present and applicability_confidence < float(
        policy["applicability_min_confidence"]
    ):
        reasons.append("applicability evidence is below its confidence threshold")
    if responsibility_present and responsibility_confidence < float(
        policy["responsibility_min_confidence"]
    ):
        reasons.append("responsibility evidence is below its confidence threshold")
    if applicability_structural_conflict:
        reasons.append("applicability structural prior conflicts with model consensus")
    return reasons


def _responsibility_evidence_is_valid(vote: ModelVote) -> bool:
    if not vote.responsibility_present or not vote.evidence:
        return False
    text = vote.evidence.lower()
    actor = re.search(
        r"\b(supplier|manufacturer|integrator|developer|development|operator|"
        r"organization|team|assessor|manager|user|customer|role|party)\b",
        text,
    )
    action = re.search(
        r"\b(shall|must|responsib|assign|ensure|perform|provide|approve|verify|validate)\w*\b",
        text,
    )
    return bool(actor and action)


def _write_outputs(
    report: ConsensusReport, output_directory: Path
) -> tuple[ConsensusReport, Path, Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "consensus-report.json"
    yaml_path = output_directory / "golden-corpus-proposal.yaml"
    review_path = output_directory / "consensus-review.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    payload = {
        "schema_version": "2.1",
        "kind": "golden_corpus_proposal",
        "matrix_id": report.matrix_id,
        "corpus_id": report.corpus_id,
        "prompt_selection": report.prompt_selection,
        "clauses": [
            {
                "clause_id": item.clause_id,
                "document_key": item.document_key,
                "reference": item.reference,
                "title": item.title,
                "clause_text": item.clause_text,
                "primary_function": (
                    item.primary_function.value if item.primary_function else None
                ),
                "primary_knowledge_kind": (
                    item.primary_knowledge_kind.value if item.primary_knowledge_kind else None
                ),
                "knowledge_kinds": [value.value for value in item.proposed_knowledge_kinds],
                "secondary_functions": [
                    value.value
                    for value in item.proposed_functions
                    if value != item.primary_function
                ],
                "applicability": {
                    "present": item.applicability_present,
                    "function": (
                        item.proposed_applicability_functions[0].value
                        if item.proposed_applicability_functions
                        else None
                    ),
                },
                "responsibility": {
                    "present": item.responsibility_present,
                    "function": (
                        item.proposed_responsibility_functions[0].value
                        if item.proposed_responsibility_functions
                        else None
                    ),
                },
                "confidence": item.confidence,
                "dimension_confidence": {
                    "statement_function": item.statement_function_confidence,
                    "knowledge_kind": item.knowledge_kind_confidence,
                    "applicability": item.applicability_confidence,
                    "responsibility": item.responsibility_confidence,
                },
                "dimension_decision_confidence": {
                    "statement_function": item.statement_function_decision_confidence,
                    "knowledge_kind": item.knowledge_kind_decision_confidence,
                    "applicability": item.applicability_decision_confidence,
                    "responsibility": item.responsibility_decision_confidence,
                },
                "consensus_category": item.category.value,
                "dimension_categories": {
                    "statement_function": item.statement_function_category.value,
                    "knowledge_kind": item.knowledge_kind_category.value,
                    "applicability": item.applicability_category.value,
                    "responsibility": item.responsibility_category.value,
                },
                "overall_status": item.overall_status.value,
                "resolution_sources": item.resolution_sources,
                "applicability_structural_conflict": item.applicability_structural_conflict,
                "adjudicated": item.adjudicated,
                "structural_prior": item.structural_prior,
                "requires_review": item.requires_review,
                "review_reasons": list(item.review_reasons),
            }
            for item in report.clauses
        ],
    }
    yaml_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    review_path.write_text(_render_review(report), encoding="utf-8")
    return report, json_path, yaml_path, review_path


_REVIEW_CATEGORY_PRIORITY = {
    ConsensusCategory.DISPUTED: 0,
    ConsensusCategory.INSUFFICIENT: 1,
    ConsensusCategory.MAJORITY: 2,
    ConsensusCategory.STRONG: 3,
    ConsensusCategory.UNANIMOUS: 4,
}


def _review_sort_key(item: ClauseConsensus) -> tuple[int, float, str, str, str]:
    return (
        _REVIEW_CATEGORY_PRIORITY[item.category],
        item.confidence,
        item.document_key,
        item.reference or "",
        item.clause_id,
    )


def _render_review(report: ConsensusReport) -> str:
    lines = [
        f"# Consensus review: {report.matrix_id}",
        "",
        "Only clauses selected by the risk-based review policy are listed.",
        "",
        f"- Models available globally: `{report.model_count}`",
        f"- Participating models per clause: min `{report.minimum_participating_models}`, "
        f"median `{report.median_participating_models:g}`, max "
        f"`{report.maximum_participating_models}`",
        "- Overall statuses: "
        + ", ".join(f"{status}={count}" for status, count in report.overall_statuses.items()),
        "- Resolution sources: "
        + (
            ", ".join(f"{source}={count}" for source, count in report.resolution_sources.items())
            or "model consensus only"
        ),
        "- Participation distribution: "
        + ", ".join(
            f"{count} voters={clauses}"
            for count, clauses in report.participation_distribution.items()
        ),
        "",
    ]
    uncertain = sorted(
        (item for item in report.clauses if item.requires_review),
        key=_review_sort_key,
    )
    if not uncertain:
        lines.extend(["No clauses require review.", ""])
        return "\n".join(lines)
    for item in uncertain:
        proposed = ", ".join(value.value for value in item.proposed_functions) or "none"
        knowledge = ", ".join(value.value for value in item.proposed_knowledge_kinds) or "none"
        applicability = (
            ", ".join(value.value for value in item.proposed_applicability_functions) or "none"
        )
        responsibility = (
            ", ".join(value.value for value in item.proposed_responsibility_functions) or "none"
        )
        lines.extend(
            [
                _review_heading(item),
                "",
                f"- Stable clause ID: `{item.clause_id}`",
                f"- Clause reference: `{item.reference or 'unavailable'}`",
                *([f"- Clause title: {item.title}"] if item.title else []),
                "",
                "### Clause text",
                "",
                "```text",
                item.clause_text or "Clause text unavailable in the evaluation dataset.",
                "```",
                "",
                f"- Overall status: `{item.overall_status.value}`",
                f"- Compatibility category: `{item.category.value}`",
                "- Dimension categories: "
                f"statement_function=`{item.statement_function_category.value}`, "
                f"knowledge_kind=`{item.knowledge_kind_category.value}`, "
                f"applicability=`{item.applicability_category.value}`, "
                f"responsibility=`{item.responsibility_category.value}`",
                f"- Resolution sources: `{item.resolution_sources or 'model_consensus'}`",
                f"- Primary/secondary statement functions: `{proposed}`",
                f"- Knowledge kinds: `{knowledge}`",
                f"- Applicability proposal: `{applicability}`",
                f"- Responsibility proposal: `{responsibility}`",
                f"- Statement-function confidence: `{item.statement_function_confidence:.3f}`",
                f"- Knowledge-kind confidence: `{item.knowledge_kind_confidence:.3f}`",
                f"- Applicability confidence: `{item.applicability_confidence:.3f}`",
                f"- Responsibility confidence: `{item.responsibility_confidence:.3f}`",
                "- Decision confidence: "
                f"statement_function=`{item.statement_function_decision_confidence:.3f}`, "
                f"knowledge_kind=`{item.knowledge_kind_decision_confidence:.3f}`, "
                f"applicability=`{item.applicability_decision_confidence:.3f}`, "
                f"responsibility=`{item.responsibility_decision_confidence:.3f}`",
                f"- Participating models: `{item.participating_models}`",
                f"- Adjudicated: `{str(item.adjudicated).lower()}`",
                f"- Structural prior: `{item.structural_prior or 'none'}`",
                "- Applicability structural conflict: "
                f"`{str(item.applicability_structural_conflict).lower()}`",
                "- Review reasons:",
                *[f"  - {reason}" for reason in item.review_reasons],
                "### Model votes",
                "",
                *_render_vote_table(item.votes),
            ]
        )
        hitl = _hitl_prefill(item, report.review_policy)
        lines.extend(
            [
                "",
                "### HITL decision",
                "",
                f"- HITL required for: {hitl['required_for']}",
                f"- Primary statement function: {hitl['primary_function']}",
                f"- Secondary statement functions: {hitl['secondary_functions']}",
                f"- Knowledge kinds: {hitl['knowledge_kinds']}",
                f"- Applicability present/function: {hitl['applicability']}",
                f"- Responsibility present/function: {hitl['responsibility']}",
                "- Rationale: ",
                "",
            ]
        )
    return "\n".join(lines)


def _hitl_prefill(item: ClauseConsensus, policy: dict[str, Any]) -> dict[str, str]:
    """Build a conservative HITL form from already accepted dimensions."""
    effective_policy = _review_policy(policy)
    statement_reliable = (
        item.primary_function is not None
        and item.category
        not in {
            ConsensusCategory.DISPUTED,
            ConsensusCategory.INSUFFICIENT,
        }
        and not (
            item.category is ConsensusCategory.MAJORITY
            and (
                item.statement_function_confidence
                < float(effective_policy["accept_majority_min_confidence"])
                or item.participating_models < int(effective_policy["accept_majority_min_models"])
            )
        )
    )
    knowledge_reliable = (
        item.primary_knowledge_kind is not None
        and item.knowledge_kind_confidence
        >= float(effective_policy["accept_majority_min_confidence"])
    )
    applicability_reliable = (
        item.applicability_present
        and item.applicability_confidence >= float(effective_policy["applicability_min_confidence"])
    ) or (not item.applicability_present and item.applicability_unanimous)
    responsibility_reliable = (
        item.responsibility_present
        and item.responsibility_confidence
        >= float(effective_policy["responsibility_min_confidence"])
    ) or (not item.responsibility_present and item.responsibility_unanimous)

    secondary = tuple(value for value in item.proposed_functions if value != item.primary_function)
    required: list[str] = []
    if not statement_reliable:
        required.append("statement functions")
    if not knowledge_reliable:
        required.append("knowledge kinds")
    if not applicability_reliable:
        required.append("applicability")
    if not responsibility_reliable:
        required.append("responsibility")

    return {
        "required_for": ", ".join(required) or "none",
        "primary_function": (
            item.primary_function.value if statement_reliable and item.primary_function else ""
        ),
        "secondary_functions": (
            ", ".join(value.value for value in secondary) or "none" if statement_reliable else ""
        ),
        "knowledge_kinds": (
            ", ".join(value.value for value in item.proposed_knowledge_kinds)
            if knowledge_reliable
            else ""
        ),
        "applicability": (
            _present_function_value(
                item.applicability_present,
                item.proposed_applicability_functions,
            )
            if applicability_reliable
            else ""
        ),
        "responsibility": (
            _present_function_value(
                item.responsibility_present,
                item.proposed_responsibility_functions,
            )
            if responsibility_reliable
            else ""
        ),
    }


def _present_function_value(present: bool, values: tuple[StrEnum, ...]) -> str:
    function = values[0].value if values else "none"
    return f"{str(present).lower()} / {function}"


def _render_vote_table(votes: tuple[ModelVote, ...]) -> list[str]:
    headers = (
        "Voter",
        "Primary statement",
        "Secondary statements",
        "Knowledge kinds",
        "Applicability",
        "Responsibility",
        "Stability",
    )
    rows = [
        (
            _vote_model_label(vote),
            _enum_value(vote.primary_function),
            _enum_values(vote.secondary_functions),
            _enum_values(vote.knowledge_kinds),
            _enum_values(vote.applicability_functions),
            _enum_values(vote.responsibility_functions),
            f"{vote.stability:.3f}",
        )
        for vote in votes
    ]
    widths = tuple(
        max([len(header), *(len(row[index]) for row in rows)])
        for index, header in enumerate(headers)
    )
    lines = [_table_row(headers, widths)]
    lines.append("| " + " | ".join("-" * width for width in widths) + " |")
    lines.extend(_table_row(row, widths) for row in rows)
    return lines


def _vote_model_label(vote: ModelVote) -> str:
    if vote.role == "voter":
        return _table_cell(vote.model_id)
    return _table_cell(f"{vote.model_id} [{vote.role}]")


def _enum_value(value: StrEnum | None) -> str:
    return _table_cell(value.value if value is not None else "none")


def _enum_values(values: tuple[StrEnum, ...]) -> str:
    return _table_cell(", ".join(value.value for value in values) or "none")


def _table_cell(value: str) -> str:
    return " ".join(value.replace("|", "\\|").splitlines())


def _table_row(values: tuple[str, ...], widths: tuple[int, ...]) -> str:
    cells = (value.ljust(width) for value, width in zip(values, widths, strict=True))
    return "| " + " | ".join(cells) + " |"


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


def _review_heading(item: ClauseConsensus) -> str:
    readable = item.reference or item.clause_id
    heading = f"## {item.document_key}:{readable}"
    if item.title:
        heading += f" — {item.title}"
    return heading
