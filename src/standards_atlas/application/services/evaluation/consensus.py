"""Model-level consensus analysis for semantic annotation matrices."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.services.evaluation.annotations import (
    ClauseEvaluationAnnotation,
)
from standards_atlas.domain.model import StatementFunction


class ConsensusCategory(StrEnum):
    UNANIMOUS = "unanimous"
    STRONG = "strong_consensus"
    MAJORITY = "majority_consensus"
    DISPUTED = "disputed"
    INSUFFICIENT = "insufficient_evidence"


class ModelVote(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    statement_functions: tuple[StatementFunction, ...]
    repetitions: int = Field(ge=1)
    stability: float = Field(ge=0.0, le=1.0)


class ClauseConsensus(BaseModel):
    model_config = ConfigDict(frozen=True)

    clause_id: str
    document_key: str
    reference: str | None = None
    category: ConsensusCategory
    proposed_functions: tuple[StatementFunction, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    participating_models: int = Field(ge=0)
    votes: tuple[ModelVote, ...] = ()
    label_support: dict[str, float] = Field(default_factory=dict)


class ConsensusReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    matrix_id: str
    corpus_id: str
    prompt_id: str
    reasoning_mode_id: str
    generated_at: datetime
    model_count: int
    clause_count: int
    categories: dict[str, int]
    clauses: tuple[ClauseConsensus, ...]


class ModelConsensusService:
    """Build one vote per model, then compare models for each clause."""

    def evaluate(
        self,
        *,
        matrix_id: str,
        corpus_id: str,
        prompt_id: str,
        reasoning_mode_id: str,
        observations: tuple[object, ...],
        output_directory: Path,
        min_models: int = 3,
        strong_threshold: float = 0.8,
        majority_threshold: float = 0.6,
        label_threshold: float = 0.6,
    ) -> tuple[ConsensusReport, Path, Path, Path]:
        selected = tuple(
            item
            for item in observations
            if item.prompt_id == prompt_id
            and item.reasoning_mode_id == reasoning_mode_id
            and getattr(item, "run_directory", None) is not None
        )
        if not selected:
            raise ValueError(
                f"no proposal runs available for consensus prompt={prompt_id!r}, "
                f"reasoning={reasoning_mode_id!r}"
            )

        predictions: dict[str, dict[str, list[ClauseEvaluationAnnotation]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for observation in selected:
            run_directory = Path(observation.run_directory)
            model_id = str(observation.model_id)
            for evaluation_path in sorted(run_directory.glob("*/evaluation.yaml")):
                payload = yaml.safe_load(evaluation_path.read_text(encoding="utf-8")) or {}
                annotation = ClauseEvaluationAnnotation.model_validate(
                    payload["annotation_candidate"]
                )
                predictions[annotation.clause.clause_id][model_id].append(annotation)

        clauses: list[ClauseConsensus] = []
        for clause_id, model_predictions in sorted(predictions.items()):
            votes: list[ModelVote] = []
            clause_reference = next(iter(next(iter(model_predictions.values())))).clause
            for model_id, model_annotations in sorted(model_predictions.items()):
                selections = [
                    tuple(sorted(item.proposal.statement_functions, key=lambda value: value.value))
                    for item in model_annotations
                ]
                counts = Counter(selections)
                selection, count = counts.most_common(1)[0]
                votes.append(
                    ModelVote(
                        model_id=model_id,
                        statement_functions=selection,
                        repetitions=len(selections),
                        stability=count / len(selections),
                    )
                )

            model_count = len(votes)
            exact_counts = Counter(vote.statement_functions for vote in votes)
            _, exact_count = exact_counts.most_common(1)[0]
            exact_agreement = exact_count / model_count if model_count else 0.0
            all_labels = sorted(
                {label for vote in votes for label in vote.statement_functions},
                key=lambda value: value.value,
            )
            label_support = {
                label.value: sum(label in vote.statement_functions for vote in votes) / model_count
                for label in all_labels
            }
            proposed = tuple(
                label for label in all_labels if label_support[label.value] >= label_threshold
            )
            confidence = max(label_support.values(), default=exact_agreement)

            if model_count < min_models:
                category = ConsensusCategory.INSUFFICIENT
            elif exact_agreement == 1.0:
                category = ConsensusCategory.UNANIMOUS
                confidence = 1.0
            elif exact_agreement >= strong_threshold:
                category = ConsensusCategory.STRONG
                confidence = exact_agreement
            elif exact_agreement >= majority_threshold:
                category = ConsensusCategory.MAJORITY
                confidence = exact_agreement
            else:
                category = ConsensusCategory.DISPUTED
                confidence = exact_agreement

            clauses.append(
                ClauseConsensus(
                    clause_id=clause_id,
                    document_key=clause_reference.document_key,
                    reference=None,
                    category=category,
                    proposed_functions=proposed,
                    confidence=confidence,
                    participating_models=model_count,
                    votes=tuple(votes),
                    label_support=label_support,
                )
            )

        category_counts = Counter(item.category.value for item in clauses)
        report = ConsensusReport(
            matrix_id=matrix_id,
            corpus_id=corpus_id,
            prompt_id=prompt_id,
            reasoning_mode_id=reasoning_mode_id,
            generated_at=datetime.now(UTC),
            model_count=len({vote.model_id for clause in clauses for vote in clause.votes}),
            clause_count=len(clauses),
            categories=dict(sorted(category_counts.items())),
            clauses=tuple(clauses),
        )
        output_directory.mkdir(parents=True, exist_ok=True)
        json_path = output_directory / "consensus-report.json"
        yaml_path = output_directory / "golden-corpus-proposal.yaml"
        review_path = output_directory / "consensus-review.md"
        json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        yaml_path.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1.0",
                    "kind": "golden_corpus_proposal",
                    "matrix_id": matrix_id,
                    "corpus_id": corpus_id,
                    "prompt_id": prompt_id,
                    "clauses": [
                        {
                            "clause_id": item.clause_id,
                            "document_key": item.document_key,
                            "statement_functions": [
                                value.value for value in item.proposed_functions
                            ],
                            "confidence": item.confidence,
                            "consensus_category": item.category.value,
                            "requires_review": item.category
                            in {
                                ConsensusCategory.MAJORITY,
                                ConsensusCategory.DISPUTED,
                                ConsensusCategory.INSUFFICIENT,
                            },
                        }
                        for item in clauses
                    ],
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        review_path.write_text(_render_review(report), encoding="utf-8")
        return report, json_path, yaml_path, review_path


def _render_review(report: ConsensusReport) -> str:
    lines = [
        f"# Consensus review: {report.matrix_id}",
        "",
        "Only clauses without strong cross-model agreement are listed.",
        "Structural classifications are intentionally outside this review.",
        "",
    ]
    uncertain = [
        item
        for item in report.clauses
        if item.category not in {ConsensusCategory.UNANIMOUS, ConsensusCategory.STRONG}
    ]
    if not uncertain:
        lines.extend(["No clauses require review.", ""])
        return "\n".join(lines)
    for item in uncertain:
        proposed = ", ".join(value.value for value in item.proposed_functions) or "none"
        lines.extend(
            [
                f"## {item.document_key}:{item.clause_id}",
                "",
                f"- Category: `{item.category.value}`",
                f"- Proposal: `{proposed}`",
                f"- Agreement: `{item.confidence:.3f}`",
                "- Model votes:",
            ]
        )
        for vote in item.votes:
            labels = ", ".join(value.value for value in vote.statement_functions) or "none"
            lines.append(
                f"  - `{vote.model_id}`: `{labels}` (repeat stability {vote.stability:.3f})"
            )
        lines.extend(["", "### HITL decision", "", "- Statement functions: ", "- Rationale: ", ""])
    return "\n".join(lines)
