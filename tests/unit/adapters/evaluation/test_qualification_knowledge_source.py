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


def _members(*, unknown: bool = False, duplicate_vote: bool = False) -> dict[str, bytes]:
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
            QualificationSelectionClause(example_id=f"e{i}", document_key="TEST", clause_id=f"c{i}")
            for i in (1, 2)
        ),
    )
    votes = tuple(
        ModelVote(
            model_id="same-model" if duplicate_vote else f"model-{i}",
            applicability_present=True,
            repetitions=3,
            stability=1.0,
        )
        for i in range(3)
    )
    consensus = ConsensusReport(
        schema_version=1,
        matrix_id="matrix",
        corpus_id="test",
        prompt_id="prompt",
        reasoning_mode_id="none",
        generated_at=NOW,
        model_count=3,
        clause_count=1,
        categories={"unanimous": 1},
        review_count=0,
        clauses=(
            ClauseConsensus(
                clause_id="c1",
                document_key="TEST",
                reference="1",
                category="unanimous",
                applicability_category="unanimous",
                applicability_present=True,
                applicability_presence_confidence=1.0,
                applicability_confidence=1.0,
                participating_models=3,
                applicability_participating_models=3,
                requires_review=False,
                votes=votes,
            ),
        ),
    )
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


def test_policy_result_materializes_only_applicability(tmp_path: Path) -> None:
    batch = load_qualification_knowledge(_archive(tmp_path, _members()))
    assert (batch.selected_clause_count, batch.unqualified_clause_count) == (2, 1)
    candidate = batch.candidates[0]
    assert candidate.patch.applicability.present is False
    assert candidate.patch.model_fields_set == {"applicability"}
    assert {item.path for item in candidate.attributes} == {"enrichments.applicability"}


def test_batch_roundtrip_and_replay_are_idempotent(tmp_path: Path) -> None:
    batch = load_qualification_knowledge(_archive(tmp_path, _members()))
    restored = KnowledgeAdoptionBatch.model_validate_json(batch.model_dump_json())
    assert restored == batch
    repository = _documents(tmp_path / "workspace")
    service = KnowledgeAdoptionService(documents=repository)
    assert service.apply(restored, write=True).written_document_keys == ("TEST",)
    assert service.apply(restored, write=True).written_document_keys == ()


def test_unknown_policy_is_not_materialized_as_negative(tmp_path: Path) -> None:
    batch = load_qualification_knowledge(_archive(tmp_path, _members(unknown=True)))
    repository = _documents(tmp_path / "workspace")
    KnowledgeAdoptionService(documents=repository).apply(batch, write=True)
    provenance = repository.load(DocumentKey(value="TEST")).clauses[0].provenance
    assert provenance.availability("enrichments.applicability") == "unknown"


def test_missing_policy_does_not_fall_back_to_gate(tmp_path: Path) -> None:
    members = _members()
    del members["applicability-policy/applicability-policy-run.json"]
    with pytest.raises(ValueError, match="exactly one applicability-policy-run"):
        load_qualification_knowledge(_archive(tmp_path, members))


def test_manifest_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    archive_path = _archive(tmp_path, _members())
    extracted = tmp_path / "extracted"
    with ZipFile(archive_path) as archive:
        archive.extractall(extracted)
    report = extracted / PREFIX / "final-consensus-report.json"
    report.write_text(report.read_text() + " ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_qualification_knowledge(extracted)


def test_zip_and_extracted_archive_have_identical_identity(tmp_path: Path) -> None:
    path = _archive(tmp_path, _members())
    extracted = tmp_path / "extracted"
    with ZipFile(path) as archive:
        archive.extractall(extracted)
    assert load_qualification_knowledge(path) == load_qualification_knowledge(extracted)


def test_cli_preview_and_write(tmp_path: Path) -> None:
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
    assert target.read_bytes() == original
    result = CliRunner().invoke(app, args + ["--write"])
    assert result.exit_code == 0, result.output
    assert target.read_bytes() != original
