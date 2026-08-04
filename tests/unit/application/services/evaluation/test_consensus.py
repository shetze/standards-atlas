import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
    _render_review,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    MatrixObservation,
)
from standards_atlas.application.services.evaluation import ModelConsensusService


def _run(
    root: Path,
    model: str,
    repeat: int,
    roles: list[str],
    *,
    applicability: list[str] | None = None,
    responsibility: list[str] | None = None,
    rationale: str | None = None,
) -> Path:
    run = root / model / f"repeat-{repeat}"
    case = run / "clause-1"
    case.mkdir(parents=True)
    payload = {
        "run": {
            "task": "statement-function-classification",
            "dataset_version": "1.0.0",
        },
        "annotation_candidate": {
            "task": "statement-function-classification",
            "lifecycle_status": "proposed",
            "clause": {
                "knowledge_domain": "functional-safety",
                "document_key": "ISO26262-6",
                "clause_id": "clause-1",
                "content_hash": (
                    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                ),
            },
            "proposal": {
                "statement_functions": roles,
                "primary_function": roles[0] if roles else None,
                "applicability_functions": applicability or [],
                "primary_applicability_function": (applicability[0] if applicability else None),
                "responsibility_functions": responsibility or [],
                "primary_responsibility_function": (responsibility[0] if responsibility else None),
                "confidence": 0.9,
                "rationale": rationale,
            },
            "generator": {
                "provider": "test",
                "model": model,
                "prompt_id": "content-only-v1",
                "generated_at": "2026-07-29T08:00:00Z",
            },
        },
    }
    (case / "evaluation.yaml").write_text(yaml.safe_dump(payload), encoding="utf-8")
    return run


def test_consensus_counts_each_model_once_after_repetition_vote(tmp_path: Path) -> None:
    observations = []
    selections = {
        "model-a": [["requirement"], ["requirement"], ["description"]],
        "model-b": [["requirement"], ["requirement"], ["requirement"]],
        "model-c": [["requirement"], ["requirement"], ["requirement"]],
        "model-d": [["requirement"], ["requirement"], ["description"]],
        "model-e": [["description"], ["description"], ["requirement"]],
    }
    for model, repeats in selections.items():
        for index, roles in enumerate(repeats, start=1):
            run = _run(tmp_path / "runs", model, index, roles)
            report = tmp_path / f"{model}-{index}.json"
            report.write_text("{}", encoding="utf-8")
            observations.append(
                MatrixObservation(
                    prompt_id="content-only",
                    model_id=model,
                    reasoning_mode_id="disabled",
                    repetition=index,
                    qualification_report=report,
                    run_directory=run,
                )
            )

    report, json_path, proposal_path, review_path = ModelConsensusService().evaluate(
        matrix_id="matrix-v1",
        corpus_id="semantic-roles-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        observations=tuple(observations),
        output_directory=tmp_path / "consensus",
        min_models=5,
    )

    clause = report.clauses[0]
    assert clause.participating_models == 5
    assert [item.value for item in clause.proposed_functions] == ["requirement"]
    assert clause.category.value == "strong_consensus"
    assert len(clause.votes) == 5
    assert json_path.is_file()
    assert proposal_path.is_file()
    assert review_path.read_text(encoding="utf-8").endswith("No clauses require review.\n")


def test_review_includes_readable_reference_title_and_clause_text(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpora"
    dataset_dir = corpus_root / "statement-function-classification" / "1.0.0"
    dataset_dir.mkdir(parents=True)
    dataset = {
        "task": "statement-function-classification",
        "version": "1.0.0",
        "examples": [
            {
                "id": "clause-1",
                "input": {
                    "content": {
                        "hash": "sha256:" + "a" * 64,
                        "text": "The supplier shall verify the software unit.",
                    },
                    "context": {
                        "knowledge_domain": "functional-safety",
                        "document_key": "ISO26262-6",
                        "clause_id": "clause-1",
                        "reference": "8.4.5",
                        "title": "Software unit verification",
                    },
                },
                "expected": {},
            }
        ],
    }
    (dataset_dir / "dataset.json").write_text(json.dumps(dataset), encoding="utf-8")

    run = _run(tmp_path / "runs", "model-a", 1, ["requirement"])
    qualification_report = tmp_path / "qualification.json"
    qualification_report.write_text("{}", encoding="utf-8")
    observation = MatrixObservation(
        prompt_id="content-only",
        model_id="model-a",
        reasoning_mode_id="disabled",
        repetition=1,
        qualification_report=qualification_report,
        run_directory=run,
    )

    report, _, proposal_path, review_path = ModelConsensusService().evaluate(
        matrix_id="matrix-v1",
        corpus_id="semantic-roles-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        observations=(observation,),
        output_directory=tmp_path / "consensus",
        corpus_root=corpus_root,
        min_models=3,
    )

    clause = report.clauses[0]
    assert clause.reference == "8.4.5"
    assert clause.title == "Software unit verification"
    assert clause.clause_text == "The supplier shall verify the software unit."

    review = review_path.read_text(encoding="utf-8")
    assert "## ISO26262-6:8.4.5 — Software unit verification" in review
    assert "- Stable clause ID: `clause-1`" in review
    assert "### Clause text" in review
    assert "The supplier shall verify the software unit." in review

    proposal = yaml.safe_load(proposal_path.read_text(encoding="utf-8"))
    assert proposal["clauses"][0]["reference"] == "8.4.5"
    assert proposal["clauses"][0]["clause_text"].startswith("The supplier")


def test_majority_consensus_is_auto_accepted_by_review_policy(tmp_path: Path) -> None:
    observations = []
    for model, roles in {
        "model-a": ["requirement"],
        "model-b": ["requirement"],
        "model-c": ["description"],
    }.items():
        run = _run(tmp_path / "runs", model, 1, roles)
        report_path = tmp_path / f"{model}.json"
        report_path.write_text("{}", encoding="utf-8")
        observations.append(
            MatrixObservation(
                prompt_id="content-only",
                model_id=model,
                repetition=1,
                qualification_report=report_path,
                run_directory=run,
            )
        )

    report, _, _, review_path = ModelConsensusService().evaluate(
        matrix_id="matrix-v2",
        corpus_id="semantic-roles-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        observations=tuple(observations),
        output_directory=tmp_path / "consensus",
        min_models=3,
        review_policy={
            "review_categories": ["disputed", "insufficient_evidence"],
            "accept_majority_min_confidence": 0.66,
            "accept_majority_min_models": 3,
        },
    )

    clause = report.clauses[0]
    assert clause.category.value == "majority_consensus"
    assert clause.primary_function.value == "requirement"
    assert clause.requires_review is False
    assert review_path.read_text(encoding="utf-8").endswith("No clauses require review.\n")


def test_responsibility_requires_actor_and_action_evidence(tmp_path: Path) -> None:
    observations = []
    for model in ("model-a", "model-b", "model-c"):
        run = _run(
            tmp_path / "runs",
            model,
            1,
            ["description"],
            responsibility=["responsibility_assignment"],
            rationale="The interval is specified as part of the requirements.",
        )
        report_path = tmp_path / f"{model}.json"
        report_path.write_text("{}", encoding="utf-8")
        observations.append(
            MatrixObservation(
                prompt_id="content-only",
                model_id=model,
                repetition=1,
                qualification_report=report_path,
                run_directory=run,
            )
        )

    report, _, _, _ = ModelConsensusService().evaluate(
        matrix_id="matrix-v2",
        corpus_id="semantic-roles-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        observations=tuple(observations),
        output_directory=tmp_path / "consensus",
        min_models=3,
    )

    clause = report.clauses[0]
    assert clause.responsibility_present is False
    assert clause.proposed_responsibility_functions == ()


def test_review_sorts_disputed_clauses_before_other_review_categories() -> None:
    report = ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="semantic-roles-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        generated_at=datetime.now(UTC),
        model_count=3,
        clause_count=4,
        categories={},
        review_count=4,
        clauses=(
            ClauseConsensus(
                clause_id="majority",
                document_key="DOC",
                reference="4",
                category=ConsensusCategory.MAJORITY,
                confidence=0.67,
                participating_models=3,
            ),
            ClauseConsensus(
                clause_id="disputed-high",
                document_key="DOC",
                reference="2",
                category=ConsensusCategory.DISPUTED,
                confidence=0.50,
                participating_models=3,
            ),
            ClauseConsensus(
                clause_id="insufficient",
                document_key="DOC",
                reference="3",
                category=ConsensusCategory.INSUFFICIENT,
                confidence=0.0,
                participating_models=1,
            ),
            ClauseConsensus(
                clause_id="disputed-low",
                document_key="DOC",
                reference="1",
                category=ConsensusCategory.DISPUTED,
                confidence=0.25,
                participating_models=3,
            ),
        ),
    )

    review = _render_review(report)

    assert review.index("## DOC:1") < review.index("## DOC:2")
    assert review.index("## DOC:2") < review.index("## DOC:3")
    assert review.index("## DOC:3") < review.index("## DOC:4")
