from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.application.semantic_qualification.cascade_replay import (
    CascadeReplayMode,
    replay_cascade,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusReport,
)
from standards_atlas.application.semantic_qualification.proposals import (
    BaselineProposalGenerator,
    ProposalRunConfig,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    build_qualification_run_selection,
    persist_qualification_run_selection,
)

IDS = ("accepted", "missing-initial", "tie", "missing-later")
RESOURCES = Path("src/standards_atlas/resources/semantic")


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _report(path: Path, values: dict[str, float]) -> None:
    clauses = tuple(
        ClauseConsensus(
            clause_id=key,
            document_key="DOC",
            category="unanimous" if value == 1 else "disputed",
            primary_function="description",
            proposed_functions=("description",),
            confidence=value,
            statement_function_confidence=value,
            statement_function_category="unanimous" if value == 1 else "disputed",
            participating_models=3,
        )
        for key, value in values.items()
    )
    report = ConsensusReport(
        matrix_id="matrix",
        corpus_id="corpus",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        generated_at=datetime(2026, 9, 12, tzinfo=UTC),
        model_count=3,
        clause_count=len(clauses),
        categories={},
        review_count=0,
        clauses=clauses,
    )
    _json(path, report.model_dump(mode="json"))


def make_run(tmp_path: Path) -> tuple[Path, Path, dict]:
    corpus = tmp_path / "corpora"
    dataset_path = corpus / "statement-function-classification" / "1.0.0" / "dataset.json"
    _json(
        dataset_path,
        {
            "task": "statement-function-classification",
            "version": "1.0.0",
            "examples": [
                {
                    "id": key,
                    "expected": {},
                    "input": {
                        "context": {
                            "clause_id": key,
                            "document_key": "DOC",
                            "knowledge_domain": "test",
                        },
                        "content": {
                            "hash": "sha256:" + "0" * 64,
                            "text": "This section describes a product.",
                        },
                    },
                }
                for key in IDS
            ],
        },
    )
    corpus_path = corpus / "corpus" / "corpus.yaml"
    corpus_path.parent.mkdir()
    corpus_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "corpus_id": "corpus",
                "task": "statement-function-classification",
                "corpus_version": "1.0.0",
                "selection_strategy": "representative_stratified",
                "seed": 1,
                "clauses": [
                    {
                        "clause": {
                            "knowledge_domain": "test",
                            "document_key": "DOC",
                            "clause_id": key,
                            "content_hash": "sha256:" + "0" * 64,
                        },
                        "strata": {},
                    }
                    for key in IDS
                ],
            }
        )
    )
    _, _, selection = build_qualification_run_selection(
        corpus_root=corpus,
        task="statement-function-classification",
        dataset_version="1.0.0",
        corpus_id="corpus",
    )
    run = tmp_path / "source"
    persist_qualification_run_selection(
        selection, run / "qualification-selection.json", corpus_root=corpus
    )
    manifest = {
        "manifest_type": "qualification_matrix",
        "schema_version": "1.6",
        "matrix_id": "matrix",
        "corpus_id": "corpus",
        "task": "statement-function-classification",
        "task_version": "1.0.0",
        "dataset_version": "1.0.0",
        "repetitions": 1,
        "prompts": [{"id": "content-only", "prompt_version": "content-only-v1"}],
        "models": [
            {"id": f"model-{index}", "provider": "fake", "model_ref": f"fake-{index}"}
            for index in range(3)
        ],
        "consensus": {
            "enabled": True,
            "prompt_id": "content-only",
            "min_models": 2,
            "structural_priors": {"enabled": False},
        },
        "execution": {
            "mode": "cascade",
            "resolution": {
                "minimum_successful_models": 1,
                "escalate_on_knowledge_kind_disagreement": False,
                "escalate_on_applicability_disagreement": False,
                "escalate_on_role_relation_disagreement": False,
                "statement_function_resolution_mode": "stage_resolver",
            },
            "stages": [
                {
                    "id": stage,
                    "models": [f"model-{index}"],
                    "apply_to": "all" if index == 0 else "unresolved",
                }
                for index, stage in enumerate(("efficient", "intermediate", "final"))
            ],
        },
    }
    manifest_path = run / "configuration" / "qualification-manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(yaml.safe_dump(manifest))
    entries = [list(IDS), ["tie", "missing-later"], ["tie"]]
    open_ids = [["tie", "missing-later"], ["tie"], []]
    exit_reasons = [
        {
            "accepted": [],
            "tie": ["statement_function_confidence"],
            "missing-later": ["statement_function_confidence"],
        },
        {"tie": ["statement_function_resolver_confidence"]},
        {"tie": []},
    ]
    stages = [
        {
            "stage_id": stage,
            "entered_clause_ids": entries[i],
            "entered_clause_count": len(entries[i]),
            "unresolved_clause_ids": open_ids[i],
            "unresolved_clause_count": len(open_ids[i]),
            "exit_reasons": exit_reasons[i],
            "newly_resolved_counts": {"responsibility": 0},
        }
        for i, stage in enumerate(("efficient", "intermediate", "final"))
    ]
    _json(
        run / "cascade-provenance.json",
        {"schema_version": "1.6", "matrix_id": "matrix", "stages": stages},
    )
    _report(
        run / "cascade/efficient/consensus-report.json",
        {"accepted": 1, "tie": 0.5, "missing-later": 0.5},
    )
    _report(run / "cascade/intermediate/consensus-report.json", {"tie": 0.5, "missing-later": 0.5})
    _report(run / "cascade/intermediate/stage-resolver/consensus-report.json", {"tie": 0.5})
    _report(run / "cascade/final/consensus-report.json", {"tie": 0.5})
    _report(run / "cascade/final/stage-resolver/consensus-report.json", {"tie": 0.5})
    return run, corpus, manifest


def _fingerprints(root: Path) -> dict:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_routing_replay_retains_missing_clauses_and_final_resolver_conflict(tmp_path: Path) -> None:
    run, _, _ = make_run(tmp_path)
    before = _fingerprints(run)
    path, markdown = replay_cascade(run=run, output_directory=tmp_path / "replay")
    report = json.loads(path.read_text())
    assert report["model_inference_performed"] is False
    assert report["selected_clause_count"] == report["accounted_clause_count"] == 4
    assert report["early_exit_count"] == 1
    assert report["unresolved_clause_count"] == 3
    assert report["requires_inference_clause_count"] == 2
    assert report["stages"][-1]["exit_reasons"]["tie"] == ["statement_function_resolver_confidence"]
    assert "statement_function" not in report["dimension_resolutions"]["tie"]
    assert report["stages"][-1]["newly_resolved_counts"]["role_relation"] == 0
    assert "historically_recorded" in markdown.read_text()
    assert _fingerprints(run) == before


def test_historical_replay_keeps_original_decisions_but_exposes_lost_evidence(
    tmp_path: Path,
) -> None:
    run, _, _ = make_run(tmp_path)
    path, _ = replay_cascade(
        run=run, output_directory=tmp_path / "history", mode=CascadeReplayMode.HISTORICAL
    )
    report = json.loads(path.read_text())
    assert report["early_exit_count"] == 1
    assert report["stages"][-1]["historically_recorded"]["unresolved_clause_count"] == 0
    assert report["stages"][-1]["completed_clause_ids"] == ["tie"]
    assert report["dimension_resolutions"] == {}
    assert report["consensus_recomputed"] is False


def test_archive_replay_and_checksum_validation(tmp_path: Path) -> None:
    run, _, _ = make_run(tmp_path)
    files = [{"path": name, "sha256": digest} for name, digest in _fingerprints(run).items()]
    _json(run / "archive-manifest.json", {"files": files})
    archive = tmp_path / "run.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for path in run.rglob("*"):
            if path.is_file():
                handle.write(path, path.relative_to(run).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    replay_cascade(run=archive, output_directory=tmp_path / "zip-replay")
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest
    _json(run / "cascade-provenance.json", {"modified": True})
    with pytest.raises(ValueError, match="checksum mismatch"):
        replay_cascade(run=run, output_directory=tmp_path / "invalid-replay")


@pytest.mark.parametrize(
    "field,value",
    [("selected_clause_count", 3), ("corpus_id", "different"), ("schema_version", "0.1")],
)
def test_selection_drift_and_unsupported_schema_fail_clearly(
    tmp_path: Path, field: str, value: object
) -> None:
    run, _, _ = make_run(tmp_path)
    path = run / "qualification-selection.json"
    selection = json.loads(path.read_text())
    selection[field] = value
    _json(path, selection)
    with pytest.raises(ValueError):
        replay_cascade(run=run, output_directory=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_snapshot_content_drift_is_not_repaired_from_shared_data(tmp_path: Path) -> None:
    run, _, _ = make_run(tmp_path)
    path = run / "qualification-dataset-snapshot.json"
    dataset = json.loads(path.read_text())
    dataset["examples"][0]["input"]["content"]["text"] = "Changed input"
    _json(path, dataset)
    with pytest.raises(ValueError, match="snapshot content changed"):
        replay_cascade(run=run, output_directory=tmp_path / "out")


def test_future_stage_without_any_archived_results_is_requires_inference(tmp_path: Path) -> None:
    run, _, _ = make_run(tmp_path)
    for path in (run / "cascade/final").rglob("*.json"):
        path.unlink()
    path, _ = replay_cascade(run=run, output_directory=tmp_path / "out")
    report = json.loads(path.read_text())
    assert report["stages"][-1]["completed_clause_count"] == 0
    assert report["requires_inference_clause_count"] == 3


def test_existing_or_source_nested_output_cannot_be_overwritten(tmp_path: Path) -> None:
    run, _, _ = make_run(tmp_path)
    with pytest.raises(ValueError, match="outside the source"):
        replay_cascade(run=run, output_directory=run / "new")
    out = tmp_path / "exists"
    out.mkdir()
    with pytest.raises(ValueError, match="new, separate"):
        replay_cascade(run=run, output_directory=out)


def test_proposals_mode_requires_explicit_source_root(tmp_path: Path) -> None:
    run, _, _ = make_run(tmp_path)
    with pytest.raises(ValueError, match="requires --runs-output"):
        replay_cascade(run=run, output_directory=tmp_path / "out", mode=CascadeReplayMode.PROPOSALS)


class FakeGateway:
    def generate_structured(self, request):
        return StructuredGenerationResult(
            {
                "statement_functions": ["description"],
                "primary_function": "description",
                "confidence": 1.0,
                "rationale": "A description.",
            },
            request.model,
            "fake",
            request.prompt_version,
            "input",
            "response",
            10,
        )


def make_proposals(corpus: Path, runs: Path) -> Path:
    config = ProposalRunConfig(
        corpus_id="corpus",
        task="statement-function-classification",
        task_version="1.0.0",
        dataset_version="1.0.0",
        prompt_version="content-only-v1",
        provider="fake",
        model="fake-0",
        seed=1,
        max_tokens=512,
        adaptive_question_max_tokens=512,
        reasoning_enabled=False,
    )
    result = BaselineProposalGenerator(FakeGateway()).run(
        config,
        resources=RESOURCES,
        corpus_root=corpus,
        output_root=runs / "qualification-runs/matrix/disabled/repeat-1",
    )
    assert result.generated == 4
    return result.run_directory


def test_proposal_replay_recomputes_and_preserves_sources_without_gateway_calls(
    tmp_path: Path, monkeypatch
) -> None:
    run, corpus, _ = make_run(tmp_path)
    runs = tmp_path / "runs"
    make_proposals(corpus, runs)
    before = _fingerprints(runs)
    monkeypatch.setattr(
        FakeGateway, "generate_structured", lambda *_: pytest.fail("no LLM calls permitted")
    )
    path, _ = replay_cascade(
        run=run,
        output_directory=tmp_path / "out",
        mode=CascadeReplayMode.PROPOSALS,
        runs_output=runs,
        resources=RESOURCES,
    )
    report = json.loads(path.read_text())
    assert report["consensus_recomputed"] is True
    assert report["early_exit_count"] == 4
    assert report["requires_inference_clause_count"] == 0
    assert _fingerprints(runs) == before
    final = json.loads((path.parent / "consensus/final/consensus-report.json").read_text())
    assert final["clause_count"] == 4


def test_changed_proposal_request_is_not_silently_reused(tmp_path: Path) -> None:
    run, corpus, _ = make_run(tmp_path)
    runs = tmp_path / "runs"
    proposals = make_proposals(corpus, runs)
    path = proposals / "accepted/request.json"
    request = json.loads(path.read_text())
    request["user_prompt"] += " changed"
    _json(path, request)
    path, _ = replay_cascade(
        run=run,
        output_directory=tmp_path / "out",
        mode=CascadeReplayMode.PROPOSALS,
        runs_output=runs,
        resources=RESOURCES,
    )
    report = json.loads(path.read_text())
    assert report["early_exit_count"] == 3
    assert any(
        item["reason"] == "request_identity_changed" for item in report["requires_inference"]
    )


def test_cli_routes_to_offline_replay_and_never_starts_server(tmp_path: Path, monkeypatch) -> None:
    from standards_atlas.adapters.llm import RamaLamaServerManager
    from standards_atlas.cli.main import app

    run, _, _ = make_run(tmp_path)
    monkeypatch.setattr(
        RamaLamaServerManager, "start", lambda *_: pytest.fail("must not start a model server")
    )
    result = CliRunner().invoke(
        app, ["evaluation", "cascade-replay", "--run", str(run), "--output", str(tmp_path / "out")]
    )
    assert result.exit_code == 0, result.output
    assert "none (offline replay)" in result.output
    assert (tmp_path / "out/cascade-replay.json").is_file()


def test_replay_manifest_defaults_do_not_change_golden_or_prompts(tmp_path: Path) -> None:
    run, _, payload = make_run(tmp_path)
    before = QualificationMatrixManifest.model_validate(payload).model_dump(mode="json")
    replay_cascade(run=run, output_directory=tmp_path / "out")
    after = yaml.safe_load((run / "configuration/qualification-manifest.yaml").read_text())
    assert before == QualificationMatrixManifest.model_validate(after).model_dump(mode="json")


def test_ambiguous_example_clause_aliases_are_rejected(tmp_path: Path) -> None:
    run, _, _ = make_run(tmp_path)
    path = run / "qualification-selection.json"
    selection = json.loads(path.read_text())
    selection["clauses"][0]["example_id"] = "missing-initial"
    selection["clauses"][1]["example_id"] = "separate-example"
    _json(path, selection)
    with pytest.raises(ValueError, match="ambiguous clause/example identity"):
        replay_cascade(run=run, output_directory=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_changed_proposal_content_hash_is_rejected(tmp_path: Path) -> None:
    run, corpus, _ = make_run(tmp_path)
    runs = tmp_path / "runs"
    proposals = make_proposals(corpus, runs)
    evaluation = proposals / "accepted/evaluation.yaml"
    payload = yaml.safe_load(evaluation.read_text())
    payload["annotation_candidate"]["clause"]["content_hash"] = "sha256:" + "f" * 64
    evaluation.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="proposal content identity mismatch"):
        replay_cascade(
            run=run,
            output_directory=tmp_path / "out",
            mode=CascadeReplayMode.PROPOSALS,
            runs_output=runs,
            resources=RESOURCES,
        )
    assert not (tmp_path / "out").exists()


def test_cli_rejects_invalid_zip_without_traceback(tmp_path: Path) -> None:
    from standards_atlas.cli.main import app

    source = tmp_path / "invalid.zip"
    source.write_bytes(b"not a zip file")
    result = CliRunner().invoke(
        app,
        ["evaluation", "cascade-replay", "--run", str(source), "--output", str(tmp_path / "out")],
    )
    assert result.exit_code == 2
    assert "Cascade replay failed" in result.output
    assert not (tmp_path / "out").exists()
