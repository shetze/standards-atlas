"""Model-level consensus analysis for semantic annotation matrices."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.evaluation.repository import (
    EvaluationDatasetRepository,
)
from standards_atlas.application.semantic_qualification.annotations import (
    ClauseEvaluationAnnotation,
)
from standards_atlas.domain.model import (
    ApplicabilityFunction,
    ResponsibilityFunction,
    StatementFunction,
)


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
    applicability_functions: tuple[ApplicabilityFunction, ...] = ()
    responsibility_functions: tuple[ResponsibilityFunction, ...] = ()
    repetitions: int = Field(ge=1)
    stability: float = Field(ge=0.0, le=1.0)


class ClauseConsensus(BaseModel):
    model_config = ConfigDict(frozen=True)

    clause_id: str
    document_key: str
    reference: str | None = None
    title: str | None = None
    clause_text: str | None = None
    category: ConsensusCategory
    proposed_functions: tuple[StatementFunction, ...] = ()
    proposed_applicability_functions: tuple[ApplicabilityFunction, ...] = ()
    proposed_responsibility_functions: tuple[ResponsibilityFunction, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    participating_models: int = Field(ge=0)
    votes: tuple[ModelVote, ...] = ()
    label_support: dict[str, float] = Field(default_factory=dict)
    applicability_support: dict[str, float] = Field(default_factory=dict)
    responsibility_support: dict[str, float] = Field(default_factory=dict)


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
        corpus_root: Path | None = None,
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
        clause_contexts = _load_clause_contexts(selected, corpus_root)
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
                    (
                        tuple(
                            sorted(item.proposal.statement_functions, key=lambda value: value.value)
                        ),
                        tuple(
                            sorted(
                                item.proposal.applicability_functions, key=lambda value: value.value
                            )
                        ),
                        tuple(
                            sorted(
                                item.proposal.responsibility_functions,
                                key=lambda value: value.value,
                            )
                        ),
                    )
                    for item in model_annotations
                ]
                counts = Counter(selections)
                selection, count = counts.most_common(1)[0]
                votes.append(
                    ModelVote(
                        model_id=model_id,
                        statement_functions=selection[0],
                        applicability_functions=selection[1],
                        responsibility_functions=selection[2],
                        repetitions=len(selections),
                        stability=count / len(selections),
                    )
                )

            model_count = len(votes)
            exact_counts = Counter(
                (
                    vote.statement_functions,
                    vote.applicability_functions,
                    vote.responsibility_functions,
                )
                for vote in votes
            )
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
            applicability_labels = sorted(
                {label for vote in votes for label in vote.applicability_functions},
                key=lambda value: value.value,
            )
            applicability_support = {
                label.value: sum(label in vote.applicability_functions for vote in votes)
                / model_count
                for label in applicability_labels
            }
            proposed_applicability = tuple(
                label
                for label in applicability_labels
                if applicability_support[label.value] >= label_threshold
            )
            responsibility_labels = sorted(
                {label for vote in votes for label in vote.responsibility_functions},
                key=lambda value: value.value,
            )
            responsibility_support = {
                label.value: sum(label in vote.responsibility_functions for vote in votes)
                / model_count
                for label in responsibility_labels
            }
            proposed_responsibility = tuple(
                label
                for label in responsibility_labels
                if responsibility_support[label.value] >= label_threshold
            )
            all_support = {
                **label_support,
                **{f"applicability:{key}": value for key, value in applicability_support.items()},
                **{f"responsibility:{key}": value for key, value in responsibility_support.items()},
            }
            confidence = max(all_support.values(), default=exact_agreement)

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

            context = clause_contexts.get(clause_id, {})
            clauses.append(
                ClauseConsensus(
                    clause_id=clause_id,
                    document_key=clause_reference.document_key,
                    reference=_optional_text(context.get("reference")),
                    title=_optional_text(context.get("title")),
                    clause_text=_optional_text(context.get("text")),
                    category=category,
                    proposed_functions=proposed,
                    proposed_applicability_functions=proposed_applicability,
                    proposed_responsibility_functions=proposed_responsibility,
                    confidence=confidence,
                    participating_models=model_count,
                    votes=tuple(votes),
                    label_support=label_support,
                    applicability_support=applicability_support,
                    responsibility_support=responsibility_support,
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
                            "reference": item.reference,
                            "title": item.title,
                            "clause_text": item.clause_text,
                            "statement_functions": [
                                value.value for value in item.proposed_functions
                            ],
                            "applicability_functions": [
                                value.value for value in item.proposed_applicability_functions
                            ],
                            "responsibility_functions": [
                                value.value for value in item.proposed_responsibility_functions
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
                f"- Category: `{item.category.value}`",
                f"- Statement-function proposal: `{proposed}`",
                f"- Applicability proposal: `{applicability}`",
                f"- Responsibility proposal: `{responsibility}`",
                f"- Agreement: `{item.confidence:.3f}`",
                "- Model votes:",
            ]
        )
        for vote in item.votes:
            labels = ", ".join(value.value for value in vote.statement_functions) or "none"
            applicability_labels = (
                ", ".join(value.value for value in vote.applicability_functions) or "none"
            )
            responsibility_labels = (
                ", ".join(value.value for value in vote.responsibility_functions) or "none"
            )
            lines.append(
                f"  - `{vote.model_id}`: statement=`{labels}`; "
                f"applicability=`{applicability_labels}`; "
                f"responsibility=`{responsibility_labels}` "
                f"(repeat stability {vote.stability:.3f})"
            )
        lines.extend(
            [
                "",
                "### HITL decision",
                "",
                "- Statement functions: ",
                "- Applicability functions: ",
                "- Responsibility functions: ",
                "- Rationale: ",
                "",
            ]
        )
    return "\n".join(lines)


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
            contexts[example.id] = {
                "reference": context.get("reference"),
                "title": context.get("title"),
                "text": content.get("text"),
            }
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
