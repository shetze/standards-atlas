"""Synthetic archive/CLI tests: no protected standards or model providers."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from typer.testing import CliRunner

from standards_atlas.adapters.evaluation.qualification_knowledge_source import (
    load_qualification_knowledge,
)
from standards_atlas.adapters.filesystem.document_repository import (
    FileSystemEngineeringDocumentRepository,
)
from standards_atlas.application.evaluation.models import EvaluationDataset, EvaluationExample
from standards_atlas.application.model.knowledge_adoption import KnowledgeAdoptionBatch
from standards_atlas.application.semantic_qualification.annotations import (
    ClauseReference,
    CorpusClause,
    EvaluationCorpusManifest,
    normalized_content_hash,
)
from standards_atlas.application.semantic_qualification.applicability_detail_enrichment import (
    build_applicability_detail_selection,
)
from standards_atlas.application.semantic_qualification.applicability_policy_runner import (
    ApplicabilityPolicyRunCase,
    ApplicabilityPolicyRunReport,
    ApplicabilityPolicyStageSummary,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ClauseConsensus,
    ConsensusReport,
    ModelVote,
)
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    build_qualification_coverage,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
    QualificationSelectionClause,
)
from standards_atlas.application.services.knowledge_adoption_service import KnowledgeAdoptionService
from standards_atlas.cli import app
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    StandardReference,
    TextBlock,
)
from standards_atlas.shared.hashing import sha256_bytes, sha256_json

NOW = datetime(2026, 9, 8, tzinfo=UTC)
PREFIX = "inputs/applicability-policy"


def _members(
    *,
    unknown: bool = False,
    duplicate_vote: bool = False,
    missing_primary: bool = False,
    process_votes: tuple[ModelVote, ...] | None = None,
    process_sources: dict[str, tuple[ModelVote, ...]] | None = None,
) -> dict[str, bytes]:
    examples = tuple(
        EvaluationExample(
            id=f"e{i}",
            input={
                "content": {
                    "text": f"Synthetic clause {i}.",
                    "hash": normalized_content_hash(f"Synthetic clause {i}."),
                },
                "context": {
                    "document_key": "TEST",
                    "clause_id": f"c{i}",
                    "reference": str(i),
                    "heading": f"Heading {i}",
                },
            },
            expected={},
        )
        for i in (1, 2)
    )
    dataset = EvaluationDataset(task="semantic", version="test", examples=examples)
    corpus = EvaluationCorpusManifest(
        corpus_id="test",
        task="semantic",
        corpus_version="test",
        seed=1,
        selection_strategy="test",
        clauses=tuple(
            CorpusClause(
                clause=ClauseReference(
                    knowledge_domain="test",
                    document_key="TEST",
                    clause_id=f"c{i}",
                    content_hash=examples[i - 1].input["content"]["hash"],
                )
            )
            for i in (1, 2)
        ),
    )
    selection = QualificationRunSelection(
        task=dataset.task,
        dataset_version=dataset.version,
        corpus_id=corpus.corpus_id,
        dataset_sha256=sha256_json(asdict(dataset)),
        corpus_sha256=sha256_json(corpus.model_dump(mode="json")),
        dataset_clause_count=2,
        corpus_clause_count=2,
        selected_clause_count=2,
        clauses=tuple(
            QualificationSelectionClause(
                example_id=f"e{i}",
                document_key="TEST",
                clause_id=f"c{i}",
            )
            for i in (1, 2)
        ),
    )
    votes = tuple(
        ModelVote(
            model_id="same-model" if duplicate_vote else f"model-{i}",
            repetitions=3,
            stability=1.0,
            primary_function="requirement",
            primary_knowledge_kind="process",
            role_semantics_present=False,
        )
        for i in range(3)
    )
    consensus = ConsensusReport(
        matrix_id="matrix",
        corpus_id="test",
        prompt_id="prompt",
        reasoning_mode_id="none",
        generated_at=NOW,
        model_count=3,
        clause_count=1,
        categories={"disputed": 1},
        review_count=1,
        clauses=(
            ClauseConsensus(
                clause_id="c1",
                document_key="TEST",
                reference="1",
                category="disputed",
                confidence=0.7,
                participating_models=3,
                requires_review=True,
                primary_function=None if missing_primary else "requirement",
                proposed_functions=("requirement",),
                primary_knowledge_kind="process",
                proposed_knowledge_kinds=("process",),
                statement_function_category="majority_consensus",
                knowledge_kind_category="majority_consensus",
                role_semantics_category="unanimous",
                applicability_present=True,
                applicability_presence_confidence=1.0,
                applicability_category="unanimous",
                votes=votes,
            ),
        ),
    )
    stages = {}
    if process_votes is not None:
        from standards_atlas.application.semantic_qualification.process_functions import (
            PROCESS_PRIMARY_FIELDS,
            PROCESS_SET_FIELDS,
            resolve_process_votes,
        )

        def process_clause(supplied, *, minimum=2):
            fields = resolve_process_votes(
                supplied,
                minimum_models=minimum,
                strong_threshold=0.8,
                majority_threshold=0.6,
                label_threshold=0.6,
            )
            return consensus.clauses[0].model_copy(update={**fields, "votes": supplied})

        current = process_clause(process_votes)
        source_paths = {}
        for dimension, supplied in (process_sources or {}).items():
            stage = "efficient" if dimension == "process_set" else "final/stage-resolver"
            stage_clause = process_clause(supplied, minimum=1)
            stages[f"cascade/{stage}/consensus-report.json"] = consensus.model_copy(
                update={"clauses": (stage_clause,)}
            ).model_dump(mode="json")
            fields = PROCESS_SET_FIELDS if dimension == "process_set" else PROCESS_PRIMARY_FIELDS
            current = current.model_copy(
                update={name: getattr(stage_clause, name) for name in fields}
            )
            source_paths[dimension] = stage
        current = current.model_copy(update={"resolution_sources": source_paths})
        consensus = consensus.model_copy(update={"clauses": (current,)})
    coverage = build_qualification_coverage(selection=selection, report=consensus)
    detail = build_applicability_detail_selection(
        run_selection=selection,
        examples=examples,
        consensus=consensus,
        coverage=coverage,
        task_version="1.0.0",
    )
    case = ApplicabilityPolicyRunCase(
        document_key="TEST",
        clause_id="c1",
        reference="1",
        gate_present=True,
        detail_selected=True,
        primary_selected=True,
        rescue_selected=True,
        confirmation_selected=False,
        primary_present=None if unknown else False,
        rescue_present=None if unknown else False,
        detail_present=None if unknown else False,
        final_present=None if unknown else False,
    )
    policy = ApplicabilityPolicyRunReport(
        generated_at=NOW,
        source_matrix_id="matrix",
        source_corpus_id="test",
        source_selection_sha256=detail.fingerprint,
        source_consensus_sha256=detail.source_consensus_sha256,
        consensus_clause_count=1,
        selected_clause_count=1,
        final_positive_count=0,
        final_negative_count=0 if unknown else 1,
        final_unknown_count=1 if unknown else 0,
        cases=(case,),
        stages=tuple(
            ApplicabilityPolicyStageSummary(
                role=role,
                task_version="1.0.0",
                prompt_version=role,
                model_id="model-policy",
                model_ref="synthetic",
                selection_sha256=detail.fingerprint,
                selected_clause_count=count,
                pending_clause_count=count,
                attempted_clause_count=count,
                reused_clause_count=0,
                fresh_prediction_count=count,
                cached_prediction_count=0,
                failed_clause_count=0,
            )
            for role, count in (("primary", 1), ("rescue", 1), ("confirmation", 0))
        ),
    )
    values = {
        **stages,
        f"{PREFIX}/qualification-selection.json": selection.model_dump(mode="json"),
        f"{PREFIX}/{selection.dataset_snapshot}": asdict(dataset),
        f"{PREFIX}/{selection.corpus_snapshot}": corpus.model_dump(mode="json"),
        f"{PREFIX}/qualification-coverage.json": coverage.model_dump(mode="json"),
        f"{PREFIX}/final-consensus-report.json": consensus.model_dump(mode="json"),
        "applicability-policy/applicability-policy-selection.json": detail.model_dump(mode="json"),
        "applicability-policy/applicability-policy-run.json": policy.model_dump(mode="json"),
    }
    return {path: json.dumps(value).encode() for path, value in values.items()}


def _archive(tmp_path: Path, members: dict[str, bytes]) -> Path:
    manifest = {
        "archive_id": "synthetic",
        "files": [
            {"path": name, "sha256": sha256_bytes(data), "size_bytes": len(data)}
            for name, data in sorted(members.items())
        ],
    }
    path = tmp_path / "run.zip"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
        archive.writestr("archive-manifest.json", json.dumps(manifest))
    return path


def _documents(workspace: Path) -> FileSystemEngineeringDocumentRepository:
    repository = FileSystemEngineeringDocumentRepository(workspace)
    repository.save(
        EngineeringDocument(
            key=DocumentKey(value="TEST"),
            title="Synthetic",
            document_type=DocumentType.OTHER,
            clauses=tuple(
                Clause(
                    id=ClauseId(value=f"c{i}"),
                    reference=StandardReference(standard="TEST", clause=str(i)),
                    clause_type=ClauseType.CLAUSE,
                    heading=f"Heading {i}",
                    content=(TextBlock(id=f"t{i}", text=f"Synthetic clause {i}."),),
                )
                for i in (1, 2)
            ),
        )
    )
    return repository


def test_policy_overrides_gate_review_does_not_block_and_retries_are_not_votes(
    tmp_path: Path,
) -> None:
    path = _archive(tmp_path, _members())
    batch = load_qualification_knowledge(path)
    assert (batch.selected_clause_count, batch.unqualified_clause_count) == (2, 1)
    candidate = batch.candidates[0]
    assert candidate.patch.semantic.applicability_present is False
    assert candidate.patch.semantic.primary_function == "requirement"
    primary = next(a for a in candidate.attributes if a.path.endswith(".primary_function"))
    assert primary.decision.valid_votes == primary.decision.supporting_votes == 3
    # Not 9 despite three repeated predictions per voter.
    assert primary.decision.label_votes == {"requirement": 3}
    assert "enrichments.semantic.process_functions" in candidate.not_evaluated
    assert not any("role_relations" in a.path for a in candidate.attributes)


def test_batch_roundtrip_preserves_omitted_fields_and_replay_is_idempotent(tmp_path: Path) -> None:
    batch = load_qualification_knowledge(_archive(tmp_path, _members()))
    restored = KnowledgeAdoptionBatch.model_validate_json(batch.model_dump_json())
    assert (
        restored.candidates[0].patch.semantic.model_fields_set
        == batch.candidates[0].patch.semantic.model_fields_set
    )
    repository = _documents(tmp_path / "workspace")
    unqualified = repository.load(DocumentKey(value="TEST")).clauses[1]
    service = KnowledgeAdoptionService(documents=repository)
    assert service.apply(restored, write=True).written_document_keys == ("TEST",)
    assert service.apply(restored, write=True).written_document_keys == ()
    assert repository.load(DocumentKey(value="TEST")).clauses[1] == unqualified


def test_unknown_policy_is_not_materialized_as_negative(tmp_path: Path) -> None:
    batch = load_qualification_knowledge(_archive(tmp_path, _members(unknown=True)))
    repository = _documents(tmp_path / "workspace")
    KnowledgeAdoptionService(documents=repository).apply(batch, write=True)
    provenance = repository.load(DocumentKey(value="TEST")).clauses[0].provenance
    assert provenance.availability("enrichments.semantic.applicability_present") == "unknown"


def test_duplicate_model_votes_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate model votes"):
        load_qualification_knowledge(_archive(tmp_path, _members(duplicate_vote=True)))


def test_missing_policy_does_not_fall_back_to_gate(tmp_path: Path) -> None:
    members = _members()
    del members["applicability-policy/applicability-policy-run.json"]
    with pytest.raises(ValueError, match="exactly one applicability-policy-run"):
        load_qualification_knowledge(_archive(tmp_path, members))


def test_manifest_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    archive_path = _archive(tmp_path, _members())
    extracted = tmp_path / "extracted"
    with ZipFile(archive_path) as archive:
        archive.extractall(extracted)  # Only this synthetic, in-test archive.
    report = extracted / PREFIX / "final-consensus-report.json"
    report.write_text(report.read_text() + " ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_qualification_knowledge(extracted)


def test_policy_from_other_consensus_is_rejected_even_with_valid_member_hash(
    tmp_path: Path,
) -> None:
    members = _members()
    name = "applicability-policy/applicability-policy-run.json"
    value = json.loads(members[name])
    value["source_consensus_sha256"] = "f" * 64
    members[name] = json.dumps(value).encode()
    with pytest.raises(ValueError, match="different final consensus"):
        load_qualification_knowledge(_archive(tmp_path, members))


def test_zip_and_extracted_archive_have_identical_identity(tmp_path: Path) -> None:
    path = _archive(tmp_path, _members())
    extracted = tmp_path / "extracted"
    with ZipFile(path) as archive:
        archive.extractall(extracted)
    assert load_qualification_knowledge(path) == load_qualification_knowledge(extracted)


def test_cli_default_preview_write_and_output_protection(tmp_path: Path) -> None:
    path = _archive(tmp_path, _members())
    workspace = tmp_path / "workspace"
    _documents(workspace)
    target = workspace / "documents" / "TEST.json"
    original = target.read_bytes()
    report = tmp_path / "adoption.json"
    args = [
        "document",
        "adopt-qualification",
        "--run",
        str(path),
        "--workspace",
        str(workspace),
        "--output",
        str(report),
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "Dry run only" in result.output
    assert target.read_bytes() == original
    assert json.loads(report.read_text())["written_document_keys"] == []
    result = CliRunner().invoke(app, args + ["--write"])
    assert result.exit_code == 0, result.output
    assert target.read_bytes() != original
    result = CliRunner().invoke(app, [*args[:-2], "--output", str(target), "--write"])
    assert result.exit_code == 2
    assert "cannot overwrite canonical" in result.output


def test_supported_set_is_not_discarded_when_primary_is_unknown(tmp_path: Path) -> None:
    batch = load_qualification_knowledge(_archive(tmp_path, _members(missing_primary=True)))
    candidate = batch.candidates[0]
    assert candidate.patch.semantic.statement_functions == ("requirement",)
    assert "primary_function" not in candidate.patch.semantic.model_fields_set
    primary = next(a for a in candidate.attributes if a.path.endswith(".primary_function"))
    assert primary.availability == "unknown"


def _process_model(model, members, primary, *, observed=True):
    return ModelVote(
        model_id=model,
        repetitions=3,
        stability=1,
        primary_function="requirement",
        primary_knowledge_kind="process",
        process_functions=members,
        primary_process_function=primary,
        process_primary_evaluated=observed,
    )


def test_adoption_keeps_decided_process_set_when_primary_ties(tmp_path):
    members = ("activity", "input")
    data = _members(
        process_votes=(
            _process_model("a", members, "activity"),
            _process_model("b", members, "input"),
            _process_model("missing", None, None, observed=False),
        )
    )
    batch = load_qualification_knowledge(
        _archive(tmp_path, data), dimensions=("process_functions",)
    )
    candidate = batch.candidates[0]
    assert candidate.patch.semantic.process_functions == members
    assert "primary_process_function" not in candidate.patch.semantic.model_fields_set
    attributes = {item.path: item for item in candidate.attributes}
    primary = attributes["enrichments.semantic.primary_process_function"]
    assert primary.availability == "unknown"
    assert primary.decision.valid_votes == 2 and primary.decision.abstained_votes == 1
    assert primary.decision.label_votes == {"activity": 1, "input": 1}
    assert attributes["enrichments.semantic.process_functions"].availability == "known"


def test_adoption_counts_explicit_empty_and_null_but_not_absent_votes(tmp_path):
    data = _members(
        process_votes=(
            _process_model("a", (), None),
            _process_model("b", (), None),
            _process_model("absent", None, None, observed=False),
        )
    )
    batch = load_qualification_knowledge(_archive(tmp_path, data))
    candidate = batch.candidates[0]
    assert candidate.patch.semantic.process_functions == ()
    assert candidate.patch.semantic.primary_process_function is None
    attrs = {a.path: a for a in candidate.attributes}
    for field in ("process_functions", "primary_process_function"):
        a = attrs[f"enrichments.semantic.{field}"]
        assert a.availability == "known"
        assert (a.decision.valid_votes, a.decision.supporting_votes) == (2, 2)
        assert a.decision.abstained_votes == 1
    primary_support = attrs["enrichments.semantic.primary_process_function"].decision
    assert primary_support.label_votes == {"none": 2}


def test_process_frozen_set_and_primary_keep_their_own_stage_support(tmp_path):
    members = ("activity", "input")
    data = _members(
        process_votes=tuple(_process_model(f"later-{i}", (), None) for i in range(4)),
        process_sources={
            "process_set": tuple(
                _process_model(f"early-{i}", members, "activity") for i in range(3)
            ),
            "process_function": (_process_model("resolver", members, "input"),),
        },
    )
    batch = load_qualification_knowledge(_archive(tmp_path, data))
    candidate = batch.candidates[0]
    assert candidate.patch.semantic.process_functions == members
    assert candidate.patch.semantic.primary_process_function == "input"
    attrs = {a.path: a for a in candidate.attributes}
    primary = attrs["enrichments.semantic.primary_process_function"].decision
    selected = attrs["enrichments.semantic.process_functions"].decision
    assert primary.stage == "final/stage-resolver"
    assert primary.model_ids == ("resolver",)
    assert primary.valid_votes == primary.supporting_votes == 1
    assert selected.stage == "efficient"
    assert selected.valid_votes == selected.supporting_votes == 3
    assert selected.model_ids == ("early-0", "early-1", "early-2")
