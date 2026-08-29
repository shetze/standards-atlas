"""Qualification-run clause selection and corpus/dataset integrity contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from standards_atlas.application.evaluation.models import EvaluationDataset, EvaluationExample
from standards_atlas.application.evaluation.repository import EvaluationDatasetRepository
from standards_atlas.application.semantic_qualification.annotations import (
    CorpusManifestRepository,
    EvaluationCorpusManifest,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_selection import (
    selected_clause_ids_by_document,
)

QUALIFICATION_SELECTION_SCHEMA_VERSION = "1.2"
QUALIFICATION_SELECTION_FILENAME = "qualification-selection.json"
QUALIFICATION_DATASET_SNAPSHOT_FILENAME = "qualification-dataset-snapshot.json"
QUALIFICATION_CORPUS_SNAPSHOT_FILENAME = "qualification-corpus-snapshot.yaml"


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
    dataset_snapshot: str = QUALIFICATION_DATASET_SNAPSHOT_FILENAME
    corpus_snapshot: str = QUALIFICATION_CORPUS_SNAPSHOT_FILENAME


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
        dataset_sha256=_dataset_fingerprint(dataset),
        corpus_sha256=_corpus_fingerprint(corpus),
        dataset_clause_count=len(dataset_coordinates),
        corpus_clause_count=len(corpus_coordinates),
        selected_clause_count=len(selection_clauses),
        clauses=selection_clauses,
    )
    return dataset, selected, selection


def persist_qualification_run_selection(
    selection: QualificationRunSelection,
    path: Path,
    *,
    corpus_root: Path,
) -> Path:
    """Persist one immutable run selection and its exact source input snapshots.

    The shared corpus repository is validated at snapshot time. Downstream stages
    must use the run-local snapshots so later corpus rebuilds cannot invalidate an
    already-started qualification run.
    """
    dataset = EvaluationDatasetRepository(corpus_root).load(
        selection.task, selection.dataset_version
    )
    corpus = CorpusManifestRepository(corpus_root).load(selection.corpus_id)
    if _dataset_fingerprint(dataset) != selection.dataset_sha256:
        raise QualificationCorpusIntegrityError(
            "qualification dataset content changed before run selection was persisted"
        )
    if _corpus_fingerprint(corpus) != selection.corpus_sha256:
        raise QualificationCorpusIntegrityError(
            "qualification corpus content changed before run selection was persisted"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    dataset_snapshot = path.parent / selection.dataset_snapshot
    corpus_snapshot = path.parent / selection.corpus_snapshot
    dataset_snapshot.write_text(
        json.dumps(asdict(dataset), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    corpus_snapshot.write_text(
        _serialize_corpus_snapshot(corpus),
        encoding="utf-8",
    )
    # Write the selection last: its presence declares that both snapshots exist.
    path.write_text(
        json.dumps(selection.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_qualification_run_selection(path: Path) -> QualificationRunSelection:
    return QualificationRunSelection.model_validate_json(path.read_text(encoding="utf-8"))


def ensure_qualification_run_snapshots(
    *,
    selection_root: Path,
    selection: QualificationRunSelection,
    corpus_root: Path,
) -> None:
    """Ensure the immutable run-local input snapshots exist and are trustworthy.

    Existing snapshots are never repaired when their content is invalid. If one or
    both snapshots are missing, both are reconstructed only when every surviving
    snapshot and the current shared sources still match the fingerprints captured
    by the persisted selection. This makes a partially cleaned run recoverable
    without weakening the qualification input integrity contract.
    """
    dataset_snapshot = selection_root / selection.dataset_snapshot
    corpus_snapshot = selection_root / selection.corpus_snapshot
    dataset_exists = dataset_snapshot.is_file()
    corpus_exists = corpus_snapshot.is_file()
    if dataset_exists and corpus_exists:
        return

    if dataset_exists:
        existing_dataset = _load_dataset_snapshot(dataset_snapshot)
        if _dataset_fingerprint(existing_dataset) != selection.dataset_sha256:
            raise QualificationCorpusIntegrityError(
                "qualification dataset snapshot content changed after selection was persisted"
            )
    if corpus_exists:
        existing_corpus = _load_corpus_snapshot(corpus_snapshot)
        if _corpus_fingerprint(existing_corpus) != selection.corpus_sha256:
            raise QualificationCorpusIntegrityError(
                "qualification corpus snapshot content changed after selection was persisted"
            )

    dataset = EvaluationDatasetRepository(corpus_root).load(
        selection.task, selection.dataset_version
    )
    corpus = CorpusManifestRepository(corpus_root).load(selection.corpus_id)
    if _dataset_fingerprint(dataset) != selection.dataset_sha256:
        raise QualificationCorpusIntegrityError(
            "qualification dataset source changed; missing run snapshot cannot be recovered"
        )
    if _corpus_fingerprint(corpus) != selection.corpus_sha256:
        raise QualificationCorpusIntegrityError(
            "qualification corpus source changed; missing run snapshot cannot be recovered"
        )

    selection_root.mkdir(parents=True, exist_ok=True)
    dataset_tmp = dataset_snapshot.with_name(dataset_snapshot.name + ".tmp")
    corpus_tmp = corpus_snapshot.with_name(corpus_snapshot.name + ".tmp")
    try:
        dataset_tmp.write_text(
            json.dumps(asdict(dataset), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        corpus_tmp.write_text(_serialize_corpus_snapshot(corpus), encoding="utf-8")
        dataset_tmp.replace(dataset_snapshot)
        corpus_tmp.replace(corpus_snapshot)
    finally:
        dataset_tmp.unlink(missing_ok=True)
        corpus_tmp.unlink(missing_ok=True)


def examples_for_persisted_selection(
    *,
    selection_root: Path,
    selection: QualificationRunSelection,
) -> tuple[EvaluationExample, ...]:
    """Reload selected examples from immutable run-local input snapshots."""
    dataset = _load_dataset_snapshot(selection_root / selection.dataset_snapshot)
    corpus = _load_corpus_snapshot(selection_root / selection.corpus_snapshot)
    if _dataset_fingerprint(dataset) != selection.dataset_sha256:
        raise QualificationCorpusIntegrityError(
            "qualification dataset snapshot content changed after selection was persisted"
        )
    if _corpus_fingerprint(corpus) != selection.corpus_sha256:
        raise QualificationCorpusIntegrityError(
            "qualification corpus snapshot content changed after selection was persisted"
        )
    by_id = {example.id: example for example in dataset.examples}
    selected: list[EvaluationExample] = []
    for clause in selection.clauses:
        example = by_id.get(clause.example_id)
        if example is None:
            raise QualificationCorpusIntegrityError(
                "persisted qualification example is missing from dataset snapshot: "
                f"{clause.example_id}"
            )
        coordinates = selected_clause_ids_by_document((example,))
        if coordinates != {clause.document_key: {clause.clause_id}}:
            raise QualificationCorpusIntegrityError(
                f"persisted qualification coordinates changed for example {clause.example_id}"
            )
        selected.append(example)
    return tuple(selected)


def qualification_snapshot_members(
    selection_root: Path,
    selection: QualificationRunSelection,
) -> tuple[tuple[Path, str], ...]:
    """Return run-local corpus snapshots for immutable qualification archives."""
    return (
        (selection_root / selection.dataset_snapshot, "inputs/corpus/dataset.json"),
        (selection_root / selection.corpus_snapshot, "inputs/corpus/corpus.yaml"),
    )


def _load_dataset_snapshot(path: Path) -> EvaluationDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return EvaluationDataset(
        task=str(payload["task"]),
        version=str(payload["version"]),
        examples=tuple(
            EvaluationExample(
                id=str(item["id"]),
                input=item["input"],
                expected=item["expected"],
                tags=tuple(item.get("tags", ())),
            )
            for item in payload.get("examples", ())
        ),
    )


def _serialize_corpus_snapshot(corpus: EvaluationCorpusManifest) -> str:
    return yaml.safe_dump(
        corpus.model_dump(mode="json"),
        sort_keys=False,
        allow_unicode=True,
    )


def _load_corpus_snapshot(path: Path) -> EvaluationCorpusManifest:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return EvaluationCorpusManifest.model_validate(payload)


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dataset_fingerprint(dataset: EvaluationDataset) -> str:
    return _canonical_sha256(asdict(dataset))


def _corpus_fingerprint(corpus: EvaluationCorpusManifest) -> str:
    return _canonical_sha256(corpus.model_dump(mode="json"))


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
