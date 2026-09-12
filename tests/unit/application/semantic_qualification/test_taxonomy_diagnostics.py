"""Filesystem, CLI, identity and immutable-archive regression tests."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.run_selection import (
    build_qualification_run_selection,
    persist_qualification_run_selection,
)
from standards_atlas.application.semantic_qualification.taxonomy_diagnostics import (
    diagnose_taxonomy_decisions,
)
from standards_atlas.cli import app


def dataset(tmp_path: Path) -> Path:
    path = tmp_path / "datasets" / "semantic-profile-classification" / "1.0.0" / "dataset.json"
    path.parent.mkdir(parents=True)
    examples = []
    for number, clause_type, heading in (
        (1, "term", "process"),
        (2, "objective", "Work products"),
        (3, "requirement", "Requirements"),
    ):
        text = f"Source text for clause {number}."
        examples.append(
            {
                "id": f"example-{number}",
                "expected": {"primary_function": "LEAK-GOLD"},
                "tags": ["LEAK-TAGS"],
                "input": {
                    "context": {
                        "document_key": "TEST-1",
                        "clause_id": f"clause-{number}",
                        "reference": str(number),
                        "knowledge_domain": "test",
                        "clause_type": clause_type,
                        "heading": heading,
                        "semantic": {"primary_function": "LEAK-SEMANTIC"},
                        "context_routing": {"target": "LEAK-ROUTING"},
                    },
                    "content": {"text": text, "hash": normalized_content_hash(text)},
                },
            }
        )
    path.write_text(
        json.dumps(
            {"task": "semantic-profile-classification", "version": "1.0.0", "examples": examples}
        ),
        encoding="utf-8",
    )
    return path


def run_archive(tmp_path: Path) -> Path:
    dataset_path = dataset(tmp_path)
    root = dataset_path.parents[2]
    corpus_path = root / "corpus" / "corpus.yaml"
    corpus_path.parent.mkdir()
    examples = json.loads(dataset_path.read_text())["examples"]
    corpus_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "corpus_id": "corpus",
                "task": "semantic-profile-classification",
                "corpus_version": "1.0.0",
                "selection_strategy": "representative_stratified",
                "seed": 1,
                "clauses": [
                    {
                        "clause": {
                            "knowledge_domain": "test",
                            "document_key": "TEST-1",
                            "clause_id": item["input"]["context"]["clause_id"],
                            "content_hash": item["input"]["content"]["hash"],
                        },
                        "strata": {},
                    }
                    for item in examples
                ],
            }
        ),
        encoding="utf-8",
    )
    _, _, selection = build_qualification_run_selection(
        corpus_root=root,
        task="semantic-profile-classification",
        dataset_version="1.0.0",
        corpus_id="corpus",
        limit=2,
    )
    source = tmp_path / "run"
    source.mkdir()
    persist_qualification_run_selection(
        selection, source / "qualification-selection.json", corpus_root=root
    )
    archive = tmp_path / "run.zip"
    items = {path.name: path.read_bytes() for path in source.iterdir()}
    items["archive-manifest.json"] = json.dumps(
        {
            "files": [
                {"path": name, "sha256": hashlib.sha256(content).hexdigest()}
                for name, content in items.items()
            ]
        }
    ).encode()
    with zipfile.ZipFile(archive, "w") as stream:
        for name, content in items.items():
            stream.writestr(name, content)
    return archive


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dataset_diagnostic_is_complete_deterministic_and_has_no_semantic_leakage(tmp_path):
    source = dataset(tmp_path)
    before = fingerprint(source)
    first, _ = diagnose_taxonomy_decisions(dataset=source, output_directory=tmp_path / "a")
    second, _ = diagnose_taxonomy_decisions(dataset=source, output_directory=tmp_path / "b")
    assert first.read_bytes() == second.read_bytes()
    assert fingerprint(source) == before
    payload = json.loads(first.read_text())
    assert payload["diagnostic_only"] is True
    assert payload["model_inference_performed"] is False
    assert payload["production_routing_changed"] is False
    assert payload["canonical_adoption_performed"] is False
    summary = payload["summary"]
    assert summary["selected_clause_count"] == summary["accounted_clause_count"] == 3
    assert summary["attribute_states"]["primary_function"] == {"hint": 2, "conflict": 1}
    assert summary["attribute_states"]["applicability_present"] == {"open": 3}
    assert "TEST" in summary["document_families"]
    assert "TEST-1" in summary["documents"]
    for output in (tmp_path / "a").iterdir():
        assert "LEAK" not in output.read_text(), output.name
    assert "pending" in (tmp_path / "a" / "taxonomy-decision-review.csv").read_text()
    assert not (tmp_path / "a" / "consensus-report.json").exists()


def test_archive_uses_exact_immutable_selection_not_all_dataset_clauses(tmp_path):
    source = run_archive(tmp_path)
    before = fingerprint(source)
    output, _ = diagnose_taxonomy_decisions(run=source, output_directory=tmp_path / "diagnostic")
    report = json.loads(output.read_text())
    assert report["summary"]["selected_clause_count"] == 2
    assert len(report["plan_fingerprints"]) == 2
    assert fingerprint(source) == before
    assert len(report["input_fingerprints"]) >= 3


def test_archive_checksum_corruption_is_rejected_without_output(tmp_path):
    source = run_archive(tmp_path)
    with zipfile.ZipFile(source) as stream:
        items = {name: stream.read(name) for name in stream.namelist()}
    items["qualification-dataset-snapshot.json"] += b" "
    with zipfile.ZipFile(source, "w") as stream:
        for name, content in items.items():
            stream.writestr(name, content)
    with pytest.raises(ValueError, match="checksum"):
        diagnose_taxonomy_decisions(run=source, output_directory=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_existing_output_is_not_overwritten(tmp_path):
    source = dataset(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("keep")
    with pytest.raises(ValueError, match="new, separate"):
        diagnose_taxonomy_decisions(dataset=source, output_directory=output)
    assert sentinel.read_text() == "keep"
    assert list(output.iterdir()) == [sentinel]


def test_output_inside_run_is_rejected(tmp_path):
    run_archive(tmp_path)
    with pytest.raises(ValueError, match="outside"):
        diagnose_taxonomy_decisions(run=tmp_path / "run", output_directory=tmp_path / "run" / "out")


@pytest.mark.parametrize("corruption", ["content", "duplicate", "empty", "example-id"])
def test_invalid_standalone_dataset_is_rejected_before_writing(tmp_path, corruption):
    source = dataset(tmp_path)
    payload = json.loads(source.read_text())
    if corruption == "content":
        payload["examples"][0]["input"]["content"]["text"] = "Changed without hash update."
    elif corruption == "duplicate":
        payload["examples"][1]["input"] = payload["examples"][0]["input"]
    elif corruption == "empty":
        payload["examples"] = []
    else:
        payload["examples"][1]["id"] = payload["examples"][0]["id"]
    source.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        diagnose_taxonomy_decisions(dataset=source, output_directory=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_cli_reports_read_only_mode_and_requires_one_source(tmp_path):
    source = dataset(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "taxonomy-decisions",
            "--dataset",
            str(source),
            "--output",
            str(tmp_path / "report"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "diagnostic only" in result.output
    missing = CliRunner().invoke(
        app, ["evaluation", "taxonomy-decisions", "--output", str(tmp_path / "missing")]
    )
    assert missing.exit_code == 2
    assert "exactly one" in missing.output
    both = CliRunner().invoke(
        app,
        [
            "evaluation",
            "taxonomy-decisions",
            "--dataset",
            str(source),
            "--run",
            str(source),
            "--output",
            str(tmp_path / "both"),
        ],
    )
    assert both.exit_code == 2
    assert not (tmp_path / "both").exists()
