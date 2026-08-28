import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusCategory,
    ConsensusReport,
    ModelVote,
    _render_review,
    _render_vote_table,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    MatrixObservation,
)
from standards_atlas.application.services.evaluation import ModelConsensusService
from standards_atlas.domain.model import ApplicabilityFunction, KnowledgeKind, StatementFunction


def _run(
    root: Path,
    model: str,
    repeat: int,
    roles: list[str],
    *,
    applicability: list[str] | None = None,
    responsibility: list[str] | None = None,
    rationale: str | None = None,
    clause_id: str = "clause-1",
) -> Path:
    run = root / model / f"repeat-{repeat}"
    case = run / clause_id
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
                "clause_id": clause_id,
                "content_hash": (
                    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                ),
            },
            "proposal": {
                "statement_functions": roles,
                "primary_function": roles[0] if roles else None,
                "applicability_present": bool(applicability),
                "applicability_functions": applicability or [],
                "primary_applicability_function": (applicability[0] if applicability else None),
                "role_semantics_present": bool(responsibility),
                "role_relation_types": responsibility or [],
                "primary_role_relation_type": (responsibility[0] if responsibility else None),
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
    assert clause.heading == "Software unit verification"
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
            responsibility=["responsible_for"],
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
    assert clause.role_relation_present is False
    assert clause.proposed_role_relation_types == ()


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


def test_consensus_filters_predictions_to_selected_example_ids(tmp_path: Path) -> None:
    observations = []
    for model in ("model-a", "model-b", "model-c"):
        run = _run(tmp_path / "runs", model, 1, ["requirement"])
        _run(
            tmp_path / "runs",
            model,
            1,
            ["description"],
            clause_id="clause-old",
        )
        report_path = tmp_path / f"{model}.json"
        report_path.write_text("{}", encoding="utf-8")
        observations.append(
            MatrixObservation(
                prompt_id="content-only",
                model_id=model,
                reasoning_mode_id="disabled",
                repetition=1,
                qualification_report=report_path,
                run_directory=run,
            )
        )

    report, _, _, _ = ModelConsensusService().evaluate(
        matrix_id="matrix-v1",
        corpus_id="semantic-roles-v1",
        prompt_id="content-only",
        reasoning_mode_id="disabled",
        observations=tuple(observations),
        output_directory=tmp_path / "consensus",
        min_models=3,
        example_ids=("clause-1",),
    )

    assert report.clause_count == 1
    assert report.clauses[0].clause_id == "clause-1"


def test_model_votes_are_rendered_as_space_padded_table() -> None:
    votes = (
        ModelVote(
            model_id="granite",
            primary_function="requirement",
            primary_knowledge_kind="technique",
            applicability_present=True,
            applicability_function="scope_definition",
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="gemma-long-model-name",
            primary_function="description",
            role_relation_present=True,
            role_relation_type="responsible_for",
            repetitions=3,
            stability=0.667,
        ),
    )

    lines = _render_vote_table(votes)

    assert lines == [
        "| Voter                 | Primary statement | Secondary statements | Knowledge kinds | "
        "Applicability    | Role relation   | Stability |",
        "| --------------------- | ----------------- | -------------------- | --------------- | "
        "---------------- | --------------- | --------- |",
        "| granite               | requirement       | none                 | technique       | "
        "scope_definition | none            | 1.000     |",
        "| gemma-long-model-name | description       | none                 | none            | "
        "none             | responsible_for | 0.667     |",
    ]
    assert all(len(line) == len(lines[0]) for line in lines)


def test_responsibility_accepts_development_function_as_actor(tmp_path: Path) -> None:
    observations = []
    selections = {
        "model-a": ["responsible_for"],
        "model-b": ["responsible_for"],
        "model-c": ["responsible_for"],
        "model-d": ["responsible_for"],
        "model-e": [],
    }
    for model, responsibility in selections.items():
        run = _run(
            tmp_path / "runs",
            model,
            1,
            ["description"],
            responsibility=responsibility,
            rationale=(
                "It is the responsibility of hardware development to ensure "
                "that the processing unit has a sufficiently low residual risk."
            ),
        )
        report_path = tmp_path / f"{model}.json"
        report_path.write_text("{}", encoding="utf-8")
        observations.append(
            MatrixObservation(
                prompt_id="content-only",
                model_id=model,
                reasoning_mode_id="disabled",
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
        min_models=5,
    )

    clause = report.clauses[0]
    assert clause.role_relation_present is True
    assert [value.value for value in clause.proposed_role_relation_types] == ["responsible_for"]
    assert clause.role_relation_support == {
        "present": 0.8,
        "responsible_for": 0.8,
    }


def test_structural_title_example_overrides_model_majority(tmp_path: Path) -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause
    from standards_atlas.application.semantic_qualification.structural_evidence import (
        derive_structural_evidence,
    )

    prior = derive_structural_evidence(
        {"title": "Example architectures", "text": "Example architectures for coexistence."}
    ).as_dict()
    votes = tuple(
        ModelVote(
            model_id=f"model-{index}",
            primary_function=StatementFunction.DESCRIPTION,
            repetitions=1,
            stability=1.0,
        )
        for index in range(3)
    )
    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior=prior,
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={
            "review_categories": {"disputed", "insufficient_evidence"},
            "accept_majority_min_confidence": 0.67,
            "accept_majority_min_models": 3,
            "applicability_min_confidence": 0.75,
            "role_relation_min_confidence": 0.8,
            "require_role_relation_evidence": True,
        },
    )
    assert result["primary_function"] is StatementFunction.EXAMPLE
    assert result["category"] is ConsensusCategory.STRONG


def test_structural_evidence_detects_guideline_and_should_not() -> None:
    from standards_atlas.application.semantic_qualification.structural_evidence import (
        derive_structural_evidence,
    )

    guideline = derive_structural_evidence(
        {"title": "Coding Standards and Style Guide", "text": "Coding guidance."}
    )
    assert guideline.primary_function is StatementFunction.GUIDELINE

    condemnation = derive_structural_evidence(
        {"title": "Overview", "text": "This annex should not be regarded as exhaustive."}
    )
    assert condemnation.primary_function is StatementFunction.CONDEMNATION
    assert StatementFunction.CONDEMNATION in condemnation.statement_functions


def test_scope_context_is_inherited_and_kept_separate_from_subtype() -> None:
    from standards_atlas.application.semantic_qualification.structural_evidence import (
        derive_structural_evidence,
    )

    evidence = derive_structural_evidence(
        {
            "title": None,
            "text": "This document applies to railway software.",
            "ancestor_headings": [{"clause_id": "DOC:1", "reference": "1", "title": "Scope"}],
        }
    )

    assert evidence.scope_context is True
    assert "ancestor-title:scope" in evidence.evidence
    assert evidence.as_dict()["scope_context"] is True
    assert evidence.as_dict()["applicability_subtype"] == "inclusion"


def test_structural_applicability_subtypes_follow_explicit_semantics() -> None:
    from standards_atlas.application.semantic_qualification.structural_evidence import (
        derive_structural_evidence,
    )

    cases = (
        ("This part applies to ASIL C and D.", "inclusion"),
        ("This part does not apply to medical equipment.", "exclusion"),
        ("These requirements apply to all systems except prototypes.", "exception"),
        (
            "If the method is used, the verification requirement is applicable to the result.",
            "applicability_condition",
        ),
    )
    for text, expected in cases:
        evidence = derive_structural_evidence({"clause_type": "scope", "text": text})
        assert evidence.applicability_subtype is not None
        assert evidence.applicability_subtype.value == expected


def test_local_unless_condition_does_not_hide_explicit_exclusion_prior() -> None:
    from standards_atlas.application.semantic_qualification.structural_evidence import (
        derive_structural_evidence,
    )

    evidence = derive_structural_evidence(
        {
            "clause_type": "scope",
            "text": (
                "This part does not apply to medical equipment. "
                "Each requirement shall be met, unless an exemption applies."
            ),
        }
    )

    assert evidence.scope_context is True
    assert evidence.applicability_subtype is not None
    assert evidence.applicability_subtype.value == "exclusion"


def test_applicability_presence_and_subtype_confidence_are_separate() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    labels = (
        "inclusion",
        "inclusion",
        "inclusion",
        "inclusion",
        "inclusion",
        "applicability_condition",
        "applicability_condition",
        "applicability_condition",
        None,
    )
    votes = tuple(
        ModelVote(
            model_id=f"model-{index}",
            primary_function=StatementFunction.DESCRIPTION,
            applicability_present=label is not None,
            applicability_function=label,
            repetitions=1,
            stability=1.0,
        )
        for index, label in enumerate(labels)
    )
    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.5,
        label_threshold=0.5,
        adjudicator_min_confidence=0.7,
        policy={
            "applicability_min_confidence": 0.75,
        },
    )

    assert result["applicability_present"] is True
    assert result["applicability_presence_confidence"] == pytest.approx(8 / 9)
    assert result["applicability_subtype_confidence"] == pytest.approx(5 / 9)
    assert result["applicability_confidence"] == pytest.approx(5 / 9)
    assert (
        "applicability subtype confidence is below its confidence threshold"
        in result["review_reasons"]
    )


def test_titled_child_does_not_blindly_inherit_scope_context() -> None:
    from standards_atlas.application.semantic_qualification.structural_evidence import (
        derive_structural_evidence,
    )

    evidence = derive_structural_evidence(
        {
            "title": "Definitions",
            "text": "Terms are defined below.",
            "ancestor_headings": [{"title": "Scope"}],
        }
    )

    assert evidence.scope_context is False
    assert evidence.applicability_subtype is None


def test_dimension_confidence_does_not_treat_none_as_positive_evidence() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = (
        ModelVote(
            model_id="a",
            primary_function=StatementFunction.REQUIREMENT,
            applicability_present=True,
            applicability_function="exclusion",
            role_relation_present=True,
            role_relation_type="responsible_for",
            evidence="The supplier shall ensure verification.",
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="b",
            primary_function=StatementFunction.REQUIREMENT,
            applicability_present=True,
            applicability_function="exclusion",
            role_relation_present=True,
            role_relation_type="responsible_for",
            evidence="The supplier shall ensure verification.",
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="c",
            primary_function=StatementFunction.DESCRIPTION,
            repetitions=1,
            stability=1.0,
        ),
    )
    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={
            "review_categories": {"disputed", "insufficient_evidence"},
            "accept_majority_min_confidence": 0.67,
            "accept_majority_min_models": 3,
            "applicability_min_confidence": 0.75,
            "role_relation_min_confidence": 0.8,
            "require_role_relation_evidence": True,
        },
    )

    assert result["confidence"] == pytest.approx(2 / 3)
    assert result["statement_function_confidence"] == pytest.approx(2 / 3)
    assert result["knowledge_kind_confidence"] == 0.0
    assert result["knowledge_kind_decision_confidence"] == 1.0
    assert result["applicability_confidence"] == pytest.approx(2 / 3)
    assert result["applicability_decision_confidence"] == pytest.approx(2 / 3)
    assert result["role_relation_confidence"] == pytest.approx(2 / 3)
    assert result["applicability_unanimous"] is False
    assert result["role_relation_unanimous"] is False
    assert (
        "majority consensus does not meet automatic-acceptance policy" in result["review_reasons"]
    )


def test_unanimous_none_knowledge_kind_is_unanimous_decision() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = tuple(
        ModelVote(
            model_id=f"model-{index}",
            primary_function=StatementFunction.DESCRIPTION,
            repetitions=1,
            stability=1.0,
        )
        for index in range(3)
    )

    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
    )

    assert result["primary_knowledge_kind"] is None
    assert result["knowledge_kind_confidence"] == 0.0
    assert result["knowledge_kind_decision_confidence"] == 1.0
    assert result["knowledge_kind_category"] is ConsensusCategory.UNANIMOUS


def test_majority_none_knowledge_kind_uses_decision_confidence() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = (
        ModelVote(
            model_id="a",
            primary_function=StatementFunction.DESCRIPTION,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="b",
            primary_function=StatementFunction.DESCRIPTION,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="c",
            primary_function=StatementFunction.DESCRIPTION,
            primary_knowledge_kind=KnowledgeKind.CONCEPT,
            repetitions=1,
            stability=1.0,
        ),
    )

    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
    )

    assert result["primary_knowledge_kind"] is None
    assert result["knowledge_kind_confidence"] == 0.0
    assert result["knowledge_kind_decision_confidence"] == pytest.approx(2 / 3)
    assert result["knowledge_kind_category"] is ConsensusCategory.MAJORITY


def test_disputed_knowledge_kind_remains_disputed() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = (
        ModelVote(
            model_id="a",
            primary_function=StatementFunction.DESCRIPTION,
            primary_knowledge_kind=KnowledgeKind.CONCEPT,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="b",
            primary_function=StatementFunction.DESCRIPTION,
            primary_knowledge_kind=KnowledgeKind.PROCESS,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="c",
            primary_function=StatementFunction.DESCRIPTION,
            primary_knowledge_kind=KnowledgeKind.TECHNIQUE_OR_MEASURE,
            repetitions=1,
            stability=1.0,
        ),
    )

    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
    )

    assert result["knowledge_kind_decision_confidence"] == pytest.approx(1 / 3)
    assert result["knowledge_kind_category"] is ConsensusCategory.DISPUTED


def test_high_role_relation_confidence_does_not_mask_missing_statement_function() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = tuple(
        ModelVote(
            model_id=f"model-{index}",
            primary_function=(None if index < 3 else StatementFunction.DESCRIPTION),
            role_relation_present=True,
            role_relation_type="responsible_for",
            evidence="The supplier shall ensure verification.",
            repetitions=1,
            stability=1.0,
        )
        for index in range(5)
    )
    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={
            "review_categories": {"disputed", "insufficient_evidence"},
            "accept_majority_min_confidence": 0.67,
            "accept_majority_min_models": 3,
            "applicability_min_confidence": 0.75,
            "role_relation_min_confidence": 0.8,
            "require_role_relation_evidence": True,
        },
    )

    assert result["category"] is ConsensusCategory.MAJORITY
    assert result["primary_function"] is None
    assert result["statement_function_confidence"] == pytest.approx(3 / 5)
    assert result["statement_function_decision_confidence"] == pytest.approx(3 / 5)
    assert result["role_relation_confidence"] == 1.0
    assert result["confidence"] == pytest.approx(3 / 5)
    assert result["requires_review"] is True


def test_review_prefills_reliable_dimensions_and_leaves_unresolved_blank() -> None:
    report = ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="semantic-roles-v1",
        prompt_id="structure-aware",
        reasoning_mode_id="disabled",
        generated_at=datetime.now(UTC),
        model_count=5,
        review_policy={
            "review_categories": ["disputed", "insufficient_evidence"],
            "accept_majority_min_confidence": 0.67,
            "accept_majority_min_models": 3,
            "applicability_min_confidence": 0.75,
            "role_relation_min_confidence": 0.80,
        },
        clause_count=1,
        categories={"strong_consensus": 1},
        review_count=1,
        clauses=(
            ClauseConsensus(
                clause_id="clause-1",
                document_key="DOC",
                reference="7.1",
                category=ConsensusCategory.STRONG,
                primary_function="requirement",
                proposed_functions=("requirement", "prerequisite"),
                primary_knowledge_kind="process",
                proposed_knowledge_kinds=("process",),
                applicability_present=True,
                proposed_applicability_functions=("exception",),
                role_relation_present=True,
                proposed_role_relation_types=("responsible_for",),
                confidence=0.8,
                statement_function_confidence=0.8,
                knowledge_kind_confidence=0.8,
                applicability_confidence=0.8,
                role_relation_confidence=0.6,
                applicability_unanimous=False,
                role_relation_unanimous=False,
                participating_models=5,
                requires_review=True,
                review_reasons=("role-relation evidence is below its confidence threshold",),
                votes=(
                    ModelVote(
                        model_id="model-a",
                        primary_function="requirement",
                        secondary_functions=("prerequisite",),
                        primary_knowledge_kind="process",
                        applicability_present=True,
                        applicability_function="exception",
                        role_relation_present=True,
                        role_relation_type="responsible_for",
                        repetitions=1,
                        stability=1.0,
                    ),
                ),
            ),
        ),
    )

    review = _render_review(report)

    assert "- HITL required for: role_relation" in review
    assert "- Primary statement function: requirement" in review
    assert "- Secondary statement functions: prerequisite" in review
    assert "- Knowledge kinds: process" in review
    assert "- Applicability present/function: true / exception" in review
    assert "- Role relation present/function: \n" in review
    assert "| Primary statement | Secondary statements |" in review
    assert "| requirement" in review and "| prerequisite" in review


def test_review_prefills_unanimous_absent_secondary_dimensions() -> None:
    report = ConsensusReport(
        matrix_id="matrix-v1",
        corpus_id="semantic-roles-v1",
        prompt_id="structure-aware",
        reasoning_mode_id="disabled",
        generated_at=datetime.now(UTC),
        model_count=3,
        clause_count=1,
        categories={"disputed": 1},
        review_count=1,
        clauses=(
            ClauseConsensus(
                clause_id="clause-1",
                document_key="DOC",
                category=ConsensusCategory.DISPUTED,
                confidence=0.33,
                statement_function_confidence=0.33,
                applicability_unanimous=True,
                role_relation_unanimous=True,
                participating_models=3,
                requires_review=True,
                review_reasons=("consensus category is disputed",),
            ),
        ),
    )

    review = _render_review(report)

    assert "- Applicability present/function: false / none" in review
    assert "- Role relation present/function: false / none" in review
    assert "- HITL required for: statement functions, knowledge kinds" in review


def test_unanimous_none_statement_function_is_high_confidence_decision() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = tuple(
        ModelVote(model_id=f"model-{index}", repetitions=1, stability=1.0) for index in range(3)
    )
    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
    )

    assert result["primary_function"] is None
    assert result["statement_function_confidence"] == 1.0
    assert result["statement_function_category"] is ConsensusCategory.UNANIMOUS


def test_cascade_resolution_override_is_authoritative_in_final_consensus() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = (
        ModelVote(
            model_id="old-a",
            primary_function=StatementFunction.REQUIREMENT,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="old-b",
            primary_function=StatementFunction.REQUIREMENT,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="resolver-a",
            primary_function=StatementFunction.DESCRIPTION,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="resolver-b",
            primary_function=StatementFunction.DESCRIPTION,
            repetitions=1,
            stability=1.0,
        ),
    )
    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
        resolution_override={
            "statement_function": {
                "value": "description",
                "confidence": 1.0,
                "category": "unanimous",
                "source": "resolver",
            }
        },
    )

    assert result["primary_function"] is StatementFunction.DESCRIPTION
    assert result["statement_function_confidence"] == 1.0
    assert result["statement_function_category"] is ConsensusCategory.UNANIMOUS
    assert result["resolution_sources"] == {"statement_function": "resolver"}


def test_scope_context_uses_applicability_as_compatibility_category() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = (
        ModelVote(
            model_id="a",
            primary_function=StatementFunction.DESCRIPTION,
            applicability_present=True,
            applicability_function="inclusion",
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="b",
            primary_function=StatementFunction.OBJECTIVE,
            applicability_present=True,
            applicability_function="inclusion",
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="c",
            applicability_present=True,
            applicability_function="inclusion",
            repetitions=1,
            stability=1.0,
        ),
    )
    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={
            "scope_context": True,
            "applicability_subtype": "inclusion",
            "confidence": 0.95,
        },
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
        scope_context=True,
    )

    assert result["statement_function_category"] is ConsensusCategory.DISPUTED
    assert result["applicability_category"] is ConsensusCategory.UNANIMOUS
    assert result["category"] is ConsensusCategory.UNANIMOUS
    assert result["overall_status"].value == "partially_resolved"


def test_applicability_structural_prior_conflict_requires_review() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = tuple(
        ModelVote(
            model_id=f"model-{index}",
            primary_function=StatementFunction.DESCRIPTION,
            applicability_present=True,
            applicability_function="exclusion",
            repetitions=1,
            stability=1.0,
        )
        for index in range(3)
    )
    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={
            "scope_context": True,
            "applicability_subtype": "exception",
            "confidence": 0.95,
        },
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
        scope_context=True,
    )

    assert result["applicability_structural_conflict"] is True
    assert result["requires_review"] is True
    assert (
        "applicability structural prior conflicts with model consensus" in result["review_reasons"]
    )


def test_resolved_structural_conflict_is_audited_but_not_reviewed() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = (
        ModelVote(
            model_id="a",
            primary_function=StatementFunction.DESCRIPTION,
            applicability_present=True,
            applicability_function="exclusion",
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="b",
            primary_function=StatementFunction.DESCRIPTION,
            applicability_present=True,
            applicability_function="exclusion",
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="c",
            primary_function=StatementFunction.DESCRIPTION,
            applicability_present=True,
            applicability_function="exception",
            repetitions=1,
            stability=1.0,
        ),
    )
    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={"applicability_subtype": "exception", "confidence": 0.95},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={
            "review_categories": {"disputed", "insufficient_evidence"},
            "accept_majority_min_confidence": 0.67,
            "accept_majority_min_models": 3,
            "applicability_min_confidence": 0.75,
            "role_relation_min_confidence": 0.8,
            "require_role_relation_evidence": True,
        },
        resolution_override={
            "applicability": {
                "present": True,
                "value": "exception",
                "confidence": 0.95,
                "category": "strong_consensus",
                "source": "resolver-stage",
                "structural_conflict_observed": True,
                "structural_conflict_unresolved": False,
            }
        },
    )

    assert result["applicability_structural_conflict_observed"] is True
    assert result["applicability_structural_conflict_unresolved"] is False
    assert result["applicability_structural_conflict"] is False
    assert (
        "applicability structural prior conflicts with model consensus"
        not in result["review_reasons"]
    )


def test_applicability_subtype_eligibility_excludes_model_from_denominator() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause
    from standards_atlas.domain.model import ApplicabilityFunction

    votes = (
        ModelVote(
            model_id="granite",
            primary_function=StatementFunction.REQUIREMENT,
            applicability_present=True,
            applicability_function=ApplicabilityFunction.INCLUSION,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="ministral",
            primary_function=StatementFunction.REQUIREMENT,
            applicability_present=True,
            applicability_function=ApplicabilityFunction.INCLUSION,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="llama",
            primary_function=StatementFunction.REQUIREMENT,
            applicability_present=True,
            applicability_function=ApplicabilityFunction.APPLICABILITY_CONDITION,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="smollm",
            primary_function=StatementFunction.REQUIREMENT,
            applicability_present=True,
            applicability_function=ApplicabilityFunction.EXCEPTION,
            repetitions=1,
            stability=1.0,
        ),
    )

    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
        model_dimension_eligibility={
            "smollm": {
                "applicability_presence": True,
                "applicability_subtype": False,
            }
        },
    )

    assert result["applicability_present"] is True
    assert result["applicability_presence_confidence"] == pytest.approx(1.0)
    assert result["applicability_subtype_confidence"] == pytest.approx(2 / 3)
    assert result["applicability_support"]["inclusion"] == pytest.approx(2 / 3)
    assert result["proposed_applicability_functions"] == (ApplicabilityFunction.INCLUSION,)


def test_applicability_presence_eligibility_excludes_model_from_presence_vote() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause
    from standards_atlas.domain.model import ApplicabilityFunction

    votes = (
        ModelVote(
            model_id="a",
            primary_function=StatementFunction.REQUIREMENT,
            applicability_present=True,
            applicability_function=ApplicabilityFunction.INCLUSION,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="b",
            primary_function=StatementFunction.REQUIREMENT,
            applicability_present=True,
            applicability_function=ApplicabilityFunction.INCLUSION,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="c",
            primary_function=StatementFunction.REQUIREMENT,
            applicability_present=True,
            applicability_function=ApplicabilityFunction.INCLUSION,
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="presence-outlier",
            primary_function=StatementFunction.REQUIREMENT,
            applicability_present=False,
            repetitions=1,
            stability=1.0,
        ),
    )

    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
        model_dimension_eligibility={
            "presence-outlier": {
                "applicability_presence": False,
                "applicability_subtype": True,
            }
        },
    )

    assert result["applicability_presence_confidence"] == pytest.approx(1.0)
    assert result["applicability_support"]["present"] == pytest.approx(1.0)


def test_open_role_relation_vote_does_not_require_legacy_relation_type() -> None:
    from standards_atlas.domain.model import RoleRelation

    vote = ModelVote(
        model_id="model-a",
        role_semantics_present=True,
        role_relations=(
            RoleRelation(
                actor="Assessor",
                relation_class="performance",
                target="compliance",
            ),
        ),
        role_relation_present=True,
        confidence=0.9,
        repetitions=1,
        stability=1.0,
    )

    assert vote.role_relation_present is True
    assert vote.role_relation_type is None
    assert vote.role_relation_types == ()


def test_role_relation_override_does_not_emit_legacy_none_label() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = (
        ModelVote(
            model_id="model-a",
            primary_function=StatementFunction.DESCRIPTION,
            role_relation_present=True,
            role_relations=(
                {
                    "actor": "Assessor",
                    "relation_class": "performance",
                    "target": "evidence",
                },
            ),
            evidence="The Assessor shall assess the evidence.",
            repetitions=1,
            stability=1.0,
        ),
    )

    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=1,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
        resolution_override={
            "role_relation": {
                "present": True,
                "confidence": 0.9,
                "category": "strong_consensus",
                "source": "cascade",
            }
        },
    )

    assert result["role_relation_present"] is True
    assert result["proposed_role_relation_types"] == ()


def test_knowledge_primary_and_set_consensus_are_reported_separately() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = (
        ModelVote(
            model_id="a",
            primary_function=StatementFunction.DESCRIPTION,
            primary_knowledge_kind=KnowledgeKind.PROCESS,
            secondary_knowledge_kinds=(KnowledgeKind.ARTIFACT,),
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="b",
            primary_function=StatementFunction.DESCRIPTION,
            primary_knowledge_kind=KnowledgeKind.PROCESS,
            secondary_knowledge_kinds=(KnowledgeKind.EVIDENCE,),
            repetitions=1,
            stability=1.0,
        ),
        ModelVote(
            model_id="c",
            primary_function=StatementFunction.DESCRIPTION,
            primary_knowledge_kind=KnowledgeKind.PROCESS,
            repetitions=1,
            stability=1.0,
        ),
    )

    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={},
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
    )

    assert result["knowledge_primary_category"] is ConsensusCategory.UNANIMOUS
    assert result["knowledge_set_category"] is ConsensusCategory.DISPUTED
    assert result["knowledge_kind_category"] is ConsensusCategory.UNANIMOUS
    assert result["knowledge_primary_unanimous"] is True
    assert result["knowledge_set_unanimous"] is False


def test_explicit_applicability_outside_scope_is_structural_evidence() -> None:
    from standards_atlas.application.semantic_qualification.structural_evidence import (
        derive_structural_evidence,
    )

    evidence = derive_structural_evidence(
        {
            "clause_type": "annex_clause",
            "title": "Achieving temporal independence",
            "text": (
                "Such an approach may only be applicable where there are no hard real "
                "time requirements."
            ),
        }
    )

    assert evidence.scope_context is False
    assert evidence.applicability_subtype is ApplicabilityFunction.APPLICABILITY_CONDITION
    assert "text:applicability_condition" in evidence.evidence


def test_generic_condition_outside_scope_is_not_applicability_evidence() -> None:
    from standards_atlas.application.semantic_qualification.structural_evidence import (
        derive_structural_evidence,
    )

    evidence = derive_structural_evidence(
        {
            "clause_type": "requirement",
            "text": "If the watchdog expires, the system shall enter the safe state.",
        }
    )

    assert evidence.scope_context is False
    assert evidence.applicability_subtype is None


def test_explicit_applicability_presence_prior_conflicts_with_negative_consensus() -> None:
    from standards_atlas.application.semantic_qualification.consensus import _resolve_clause

    votes = tuple(
        ModelVote(
            model_id=f"model-{index}",
            primary_function=StatementFunction.DESCRIPTION,
            applicability_present=False,
            repetitions=1,
            stability=1.0,
        )
        for index in range(3)
    )
    result = _resolve_clause(
        votes=votes,
        adjudicator_vote=None,
        structural_prior={
            "applicability_subtype": "applicability_condition",
            "confidence": 0.95,
            "evidence": ["text:applicability_condition"],
        },
        minimum_models=3,
        strong_threshold=0.8,
        majority_threshold=0.6,
        label_threshold=0.6,
        adjudicator_min_confidence=0.7,
        policy={},
        scope_context=False,
    )

    assert result["applicability_present"] is True
    assert result["proposed_applicability_functions"] == (
        ApplicabilityFunction.APPLICABILITY_CONDITION,
    )
    assert result["applicability_structural_conflict_observed"] is True
    assert result["applicability_structural_conflict_unresolved"] is True
    assert result["requires_review"] is True
