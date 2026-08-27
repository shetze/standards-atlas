from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationCorpusIntegrityError,
    build_qualification_run_selection,
    examples_for_persisted_selection,
    load_qualification_run_selection,
    persist_qualification_run_selection,
)


def _write_inputs(
    root: Path, *, dataset_clauses: tuple[str, ...], corpus_clauses: tuple[str, ...]
) -> None:
    dataset_path = root / "statement-function-classification" / "2.2.0" / "dataset.json"
    dataset_path.parent.mkdir(parents=True)
    dataset_path.write_text(
        json.dumps(
            {
                "task": "statement-function-classification",
                "version": "2.2.0",
                "examples": [
                    {
                        "id": clause_id,
                        "input": {
                            "context": {
                                "document_key": "DOC",
                                "clause_id": clause_id,
                            },
                            "content": f"content {clause_id}",
                        },
                        "expected": {},
                    }
                    for clause_id in dataset_clauses
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    corpus_path = root / "corpus-v1" / "corpus.yaml"
    corpus_path.parent.mkdir(parents=True)
    corpus_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "corpus_id": "corpus-v1",
                "task": "statement-function-classification",
                "corpus_version": "2.2.0",
                "selection_strategy": "representative_stratified",
                "seed": 1,
                "clauses": [
                    {
                        "clause": {
                            "knowledge_domain": "test",
                            "document_key": "DOC",
                            "clause_id": clause_id,
                            "content_hash": "sha256:" + "0" * 64,
                        },
                        "strata": {},
                    }
                    for clause_id in corpus_clauses
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_selection_rejects_dataset_corpus_drift(tmp_path: Path) -> None:
    _write_inputs(tmp_path, dataset_clauses=("one", "two"), corpus_clauses=("one", "three"))

    with pytest.raises(
        QualificationCorpusIntegrityError, match="do not describe the same clause set"
    ):
        build_qualification_run_selection(
            corpus_root=tmp_path,
            task="statement-function-classification",
            dataset_version="2.2.0",
            corpus_id="corpus-v1",
            limit=2,
        )


def test_selection_persists_limit_and_reuses_exact_clause_set(tmp_path: Path) -> None:
    _write_inputs(
        tmp_path,
        dataset_clauses=("one", "two", "three"),
        corpus_clauses=("one", "two", "three"),
    )

    _, selected, selection = build_qualification_run_selection(
        corpus_root=tmp_path,
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="corpus-v1",
        limit=2,
    )
    path = persist_qualification_run_selection(selection, tmp_path / "run" / "selection.json")
    loaded = load_qualification_run_selection(path)
    reloaded = examples_for_persisted_selection(corpus_root=tmp_path, selection=loaded)

    assert tuple(item.id for item in selected) == ("one", "two")
    assert tuple(item.id for item in reloaded) == ("one", "two")
    assert loaded.requested_limit == 2
    assert loaded.selected_clause_count == 2
    assert [(item.document_key, item.clause_id) for item in loaded.clauses] == [
        ("DOC", "one"),
        ("DOC", "two"),
    ]


def test_persisted_selection_rejects_corpus_change(tmp_path: Path) -> None:
    _write_inputs(tmp_path, dataset_clauses=("one",), corpus_clauses=("one",))
    _, _, selection = build_qualification_run_selection(
        corpus_root=tmp_path,
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="corpus-v1",
    )
    corpus_path = tmp_path / "corpus-v1" / "corpus.yaml"
    corpus_path.write_text(
        corpus_path.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8"
    )

    with pytest.raises(QualificationCorpusIntegrityError, match="corpus manifest changed"):
        examples_for_persisted_selection(corpus_root=tmp_path, selection=selection)
