"""Qualification-run clause selection and corpus/dataset integrity contract."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.evaluation.models import EvaluationDataset, EvaluationExample
from standards_atlas.application.evaluation.repository import EvaluationDatasetRepository
from standards_atlas.application.semantic_qualification.annotations import CorpusManifestRepository
from standards_atlas.application.semantic_qualification.semantic_extraction_selection import (
    selected_clause_ids_by_document,
)
from standards_atlas.shared.hashing import sha256_file

QUALIFICATION_SELECTION_SCHEMA_VERSION = "1.0"
QUALIFICATION_SELECTION_FILENAME = "qualification-selection.json"


class QualificationSelectionClause(BaseModel):
    model_config = ConfigDict(frozen=True)

    example_id: str = Field(min_length=1)
    document_key: str = Field(min_length=1)
    clause_id: str = Field(min_length=1)


class QualificationRunSelection(BaseModel):
    """Immutable declaration of the clauses selected for one qualification run."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = QUALIFICATION_SELECTION_SCHEMA_VERSION
    task: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    corpus_id: str = Field(min_length=1)
    requested_limit: int | None = Field(default=None, ge=1)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_clause_count: int = Field(ge=0)
    corpus_clause_count: int = Field(ge=0)
    selected_clause_count: int = Field(ge=0)
    clauses: tuple[QualificationSelectionClause, ...]


class QualificationCorpusIntegrityError(ValueError):
    """Raised when qualification inputs no longer describe the same corpus."""


def build_qualification_run_selection(
    *,
    corpus_root: Path,
    task: str,
    dataset_version: str,
    corpus_id: str,
    limit: int | None = None,
    selected_example_ids: Iterable[str] | None = None,
) -> tuple[EvaluationDataset, tuple[EvaluationExample, ...], QualificationRunSelection]:
    """Validate corpus/dataset identity and create one deterministic run selection."""
    dataset_path = _dataset_path(corpus_root, task, dataset_version)
    corpus_path = CorpusManifestRepository(corpus_root).path_for(corpus_id)
    dataset = EvaluationDatasetRepository(corpus_root).load(task, dataset_version)
    corpus = CorpusManifestRepository(corpus_root).load(corpus_id)

    dataset_coordinates = _dataset_coordinates(dataset.examples)
    corpus_coordinates = tuple(
        (item.clause.document_key, item.clause.clause_id) for item in corpus.clauses
    )
    _require_unique("dataset", dataset_coordinates)
    _require_unique("corpus", corpus_coordinates)
    dataset_set = set(dataset_coordinates)
    corpus_set = set(corpus_coordinates)
    if dataset_set != corpus_set:
        missing_from_corpus = sorted(dataset_set - corpus_set)
        missing_from_dataset = sorted(corpus_set - dataset_set)
        details = []
        if missing_from_corpus:
            sample = ", ".join(f"{doc}/{clause}" for doc, clause in missing_from_corpus[:5])
            details.append("dataset-only=" + sample)
        if missing_from_dataset:
            sample = ", ".join(f"{doc}/{clause}" for doc, clause in missing_from_dataset[:5])
            details.append("corpus-only=" + sample)
        detail_text = "; ".join(details)
        raise QualificationCorpusIntegrityError(
            "qualification dataset and corpus manifest do not describe the same clause set "
            f"({len(dataset_set)} dataset vs {len(corpus_set)} corpus clauses; {detail_text})"
        )

    selected = _select_examples(
        dataset.examples,
        limit=limit,
        selected_example_ids=selected_example_ids,
    )
    selection_clauses = tuple(
        QualificationSelectionClause(
            example_id=example.id,
            document_key=coordinate[0],
            clause_id=coordinate[1],
        )
        for example, coordinate in zip(selected, _dataset_coordinates(selected), strict=True)
    )
    selection = QualificationRunSelection(
        task=task,
        dataset_version=dataset_version,
        corpus_id=corpus_id,
        requested_limit=limit,
        dataset_sha256=sha256_file(dataset_path),
        corpus_sha256=sha256_file(corpus_path),
        dataset_clause_count=len(dataset_coordinates),
        corpus_clause_count=len(corpus_coordinates),
        selected_clause_count=len(selection_clauses),
        clauses=selection_clauses,
    )
    return dataset, selected, selection


def persist_qualification_run_selection(selection: QualificationRunSelection, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(selection.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_qualification_run_selection(path: Path) -> QualificationRunSelection:
    return QualificationRunSelection.model_validate_json(path.read_text(encoding="utf-8"))


def examples_for_persisted_selection(
    *,
    corpus_root: Path,
    selection: QualificationRunSelection,
) -> tuple[EvaluationExample, ...]:
    """Reload selected examples while proving the persisted input snapshots are unchanged."""
    dataset_path = _dataset_path(corpus_root, selection.task, selection.dataset_version)
    corpus_path = CorpusManifestRepository(corpus_root).path_for(selection.corpus_id)
    if sha256_file(dataset_path) != selection.dataset_sha256:
        raise QualificationCorpusIntegrityError(
            "qualification dataset changed after clause selection was persisted"
        )
    if sha256_file(corpus_path) != selection.corpus_sha256:
        raise QualificationCorpusIntegrityError(
            "qualification corpus manifest changed after clause selection was persisted"
        )
    dataset = EvaluationDatasetRepository(corpus_root).load(
        selection.task, selection.dataset_version
    )
    by_id = {example.id: example for example in dataset.examples}
    selected: list[EvaluationExample] = []
    for clause in selection.clauses:
        example = by_id.get(clause.example_id)
        if example is None:
            raise QualificationCorpusIntegrityError(
                f"persisted qualification example is missing from dataset: {clause.example_id}"
            )
        coordinates = selected_clause_ids_by_document((example,))
        if coordinates != {clause.document_key: {clause.clause_id}}:
            raise QualificationCorpusIntegrityError(
                f"persisted qualification coordinates changed for example {clause.example_id}"
            )
        selected.append(example)
    return tuple(selected)


def _dataset_path(corpus_root: Path, task: str, version: str) -> Path:
    direct = corpus_root / task / version / "dataset.json"
    if direct.is_file():
        return direct
    if task == "semantic-profile-classification":
        return corpus_root / "statement-function-classification" / version / "dataset.json"
    return direct


def _dataset_coordinates(examples: Iterable[EvaluationExample]) -> tuple[tuple[str, str], ...]:
    coordinates: list[tuple[str, str]] = []
    for example in examples:
        selected = selected_clause_ids_by_document((example,))
        if len(selected) != 1:
            raise QualificationCorpusIntegrityError(
                f"evaluation example {example.id!r} has no unambiguous document/clause coordinates"
            )
        document_key, clause_ids = next(iter(selected.items()))
        if len(clause_ids) != 1:
            raise QualificationCorpusIntegrityError(
                f"evaluation example {example.id!r} has no unambiguous clause coordinate"
            )
        coordinates.append((document_key, next(iter(clause_ids))))
    return tuple(coordinates)


def _require_unique(label: str, coordinates: tuple[tuple[str, str], ...]) -> None:
    if len(coordinates) == len(set(coordinates)):
        return
    seen: set[tuple[str, str]] = set()
    duplicate: tuple[str, str] | None = None
    for item in coordinates:
        if item in seen:
            duplicate = item
            break
        seen.add(item)
    assert duplicate is not None
    raise QualificationCorpusIntegrityError(
        f"{label} contains duplicate clause coordinate: {duplicate[0]}/{duplicate[1]}"
    )


def _select_examples(
    examples: tuple[EvaluationExample, ...],
    *,
    limit: int | None,
    selected_example_ids: Iterable[str] | None,
) -> tuple[EvaluationExample, ...]:
    if selected_example_ids is None:
        return tuple(examples[:limit] if limit is not None else examples)
    requested = tuple(selected_example_ids)
    known_ids = {example.id for example in examples}
    unknown = tuple(example_id for example_id in requested if example_id not in known_ids)
    if unknown:
        unknown_text = ", ".join(unknown[:5])
        raise QualificationCorpusIntegrityError(
            "selected qualification clauses are not present in the dataset: " + unknown_text
        )
    requested_set = set(requested)
    return tuple(example for example in examples if example.id in requested_set)
