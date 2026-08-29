from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationCorpusIntegrityError,
    build_qualification_run_selection,
    ensure_qualification_run_snapshots,
    examples_for_persisted_selection,
    load_qualification_run_selection,
    persist_qualification_run_selection,
    qualification_snapshot_members,
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
    path = persist_qualification_run_selection(
        selection, tmp_path / "run" / "selection.json", corpus_root=tmp_path
    )
    loaded = load_qualification_run_selection(path)
    reloaded = examples_for_persisted_selection(selection_root=path.parent, selection=loaded)

    assert tuple(item.id for item in selected) == ("one", "two")
    assert tuple(item.id for item in reloaded) == ("one", "two")
    assert loaded.requested_limit == 2
    assert loaded.selected_clause_count == 2
    assert [(item.document_key, item.clause_id) for item in loaded.clauses] == [
        ("DOC", "one"),
        ("DOC", "two"),
    ]


def test_persisted_selection_is_independent_of_later_shared_corpus_rewrites(
    tmp_path: Path,
) -> None:
    _write_inputs(tmp_path, dataset_clauses=("one",), corpus_clauses=("one",))
    _, _, selection = build_qualification_run_selection(
        corpus_root=tmp_path,
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="corpus-v1",
    )
    selection_path = persist_qualification_run_selection(
        selection, tmp_path / "run" / "selection.json", corpus_root=tmp_path
    )

    dataset_path = tmp_path / "statement-function-classification" / "2.2.0" / "dataset.json"
    dataset_payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    dataset_payload["examples"][0]["input"]["content"] = "rebuilt shared content"
    dataset_path.write_text(json.dumps(dataset_payload, indent=2) + "\n", encoding="utf-8")
    corpus_path = tmp_path / "corpus-v1" / "corpus.yaml"
    corpus_payload = yaml.safe_load(corpus_path.read_text(encoding="utf-8"))
    corpus_payload["seed"] = 2
    corpus_path.write_text(yaml.safe_dump(corpus_payload, sort_keys=False), encoding="utf-8")

    reloaded = examples_for_persisted_selection(
        selection_root=selection_path.parent, selection=selection
    )

    assert tuple(item.id for item in reloaded) == ("one",)
    assert reloaded[0].input["content"] == "content one"


def test_selection_persistence_rejects_source_change_before_snapshot(tmp_path: Path) -> None:
    _write_inputs(tmp_path, dataset_clauses=("one",), corpus_clauses=("one",))
    _, _, selection = build_qualification_run_selection(
        corpus_root=tmp_path,
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="corpus-v1",
    )
    dataset_path = tmp_path / "statement-function-classification" / "2.2.0" / "dataset.json"
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    payload["examples"][0]["input"]["content"] = "changed before snapshot"
    dataset_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(QualificationCorpusIntegrityError, match="before run selection"):
        persist_qualification_run_selection(
            selection, tmp_path / "run" / "selection.json", corpus_root=tmp_path
        )

    assert not (tmp_path / "run" / "selection.json").exists()


def test_persisted_selection_rejects_dataset_snapshot_change(tmp_path: Path) -> None:
    _write_inputs(tmp_path, dataset_clauses=("one",), corpus_clauses=("one",))
    _, _, selection = build_qualification_run_selection(
        corpus_root=tmp_path,
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="corpus-v1",
    )
    selection_path = persist_qualification_run_selection(
        selection, tmp_path / "run" / "selection.json", corpus_root=tmp_path
    )
    snapshot_path = selection_path.parent / selection.dataset_snapshot
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["examples"][0]["input"]["content"] = "tampered snapshot"
    snapshot_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(QualificationCorpusIntegrityError, match="dataset snapshot content changed"):
        examples_for_persisted_selection(selection_root=selection_path.parent, selection=selection)


def test_persisted_selection_rejects_corpus_snapshot_change(tmp_path: Path) -> None:
    _write_inputs(tmp_path, dataset_clauses=("one",), corpus_clauses=("one",))
    _, _, selection = build_qualification_run_selection(
        corpus_root=tmp_path,
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="corpus-v1",
    )
    selection_path = persist_qualification_run_selection(
        selection, tmp_path / "run" / "selection.json", corpus_root=tmp_path
    )
    snapshot_path = selection_path.parent / selection.corpus_snapshot
    payload = yaml.safe_load(snapshot_path.read_text(encoding="utf-8"))
    payload["seed"] = 2
    snapshot_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(QualificationCorpusIntegrityError, match="corpus snapshot content changed"):
        examples_for_persisted_selection(selection_root=selection_path.parent, selection=selection)


def test_archive_members_use_run_local_input_snapshots(tmp_path: Path) -> None:
    _write_inputs(tmp_path, dataset_clauses=("one",), corpus_clauses=("one",))
    _, _, selection = build_qualification_run_selection(
        corpus_root=tmp_path,
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="corpus-v1",
    )
    selection_path = persist_qualification_run_selection(
        selection, tmp_path / "run" / "selection.json", corpus_root=tmp_path
    )

    members = qualification_snapshot_members(selection_path.parent, selection)

    assert members == (
        (
            selection_path.parent / selection.dataset_snapshot,
            "inputs/corpus/dataset.json",
        ),
        (
            selection_path.parent / selection.corpus_snapshot,
            "inputs/corpus/corpus.yaml",
        ),
    )
    assert all(path.is_file() for path, _ in members)


def test_missing_run_snapshots_are_recovered_from_matching_shared_inputs(
    tmp_path: Path,
) -> None:
    _write_inputs(tmp_path, dataset_clauses=("one",), corpus_clauses=("one",))
    _, _, selection = build_qualification_run_selection(
        corpus_root=tmp_path,
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="corpus-v1",
    )
    selection_path = persist_qualification_run_selection(
        selection, tmp_path / "run" / "selection.json", corpus_root=tmp_path
    )
    dataset_snapshot = selection_path.parent / selection.dataset_snapshot
    corpus_snapshot = selection_path.parent / selection.corpus_snapshot
    dataset_snapshot.unlink()
    corpus_snapshot.unlink()

    ensure_qualification_run_snapshots(
        selection_root=selection_path.parent,
        selection=selection,
        corpus_root=tmp_path,
    )

    assert dataset_snapshot.is_file()
    assert corpus_snapshot.is_file()
    reloaded = examples_for_persisted_selection(
        selection_root=selection_path.parent, selection=selection
    )
    assert tuple(item.id for item in reloaded) == ("one",)


def test_missing_snapshot_recovery_rejects_changed_shared_dataset(tmp_path: Path) -> None:
    _write_inputs(tmp_path, dataset_clauses=("one",), corpus_clauses=("one",))
    _, _, selection = build_qualification_run_selection(
        corpus_root=tmp_path,
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="corpus-v1",
    )
    selection_path = persist_qualification_run_selection(
        selection, tmp_path / "run" / "selection.json", corpus_root=tmp_path
    )
    (selection_path.parent / selection.dataset_snapshot).unlink()
    dataset_path = tmp_path / "statement-function-classification" / "2.2.0" / "dataset.json"
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    payload["examples"][0]["input"]["content"] = "changed shared content"
    dataset_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        QualificationCorpusIntegrityError, match="dataset source changed.*cannot be recovered"
    ):
        ensure_qualification_run_snapshots(
            selection_root=selection_path.parent,
            selection=selection,
            corpus_root=tmp_path,
        )


def test_missing_snapshot_recovery_rejects_corrupt_surviving_snapshot(tmp_path: Path) -> None:
    _write_inputs(tmp_path, dataset_clauses=("one",), corpus_clauses=("one",))
    _, _, selection = build_qualification_run_selection(
        corpus_root=tmp_path,
        task="statement-function-classification",
        dataset_version="2.2.0",
        corpus_id="corpus-v1",
    )
    selection_path = persist_qualification_run_selection(
        selection, tmp_path / "run" / "selection.json", corpus_root=tmp_path
    )
    (selection_path.parent / selection.dataset_snapshot).unlink()
    corpus_snapshot = selection_path.parent / selection.corpus_snapshot
    payload = yaml.safe_load(corpus_snapshot.read_text(encoding="utf-8"))
    payload["seed"] = 99
    corpus_snapshot.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(QualificationCorpusIntegrityError, match="corpus snapshot content changed"):
        ensure_qualification_run_snapshots(
            selection_root=selection_path.parent,
            selection=selection,
            corpus_root=tmp_path,
        )
