from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from standards_atlas.adapters.filesystem import (
    FileSystemAssertionExperimentRepository,
    FileSystemContextSourcePackageRepository,
)
from standards_atlas.adapters.mcp.configuration import McpServerConfig
from standards_atlas.adapters.mcp.development import (
    McpCodexOptimizationService,
    McpDevelopmentScope,
)
from standards_atlas.application.assertion_qualification.assertion_review import (
    AssertionReviewSurface,
    AssertionReviewWorkbenchCase,
    ReviewOntologyOption,
    package_from_cases,
    write_assertion_review_package,
)
from standards_atlas.application.assertion_qualification.codex_optimization import (
    CodexOptimizationProposal,
)
from standards_atlas.application.assertion_qualification.experiment import (
    ExperimentBudget,
    manifest_sha256,
    plan_assertion_experiment,
)
from standards_atlas.application.assertion_qualification.models import (
    AssertionAuditBinding,
    AssertionGoldenCase,
    AssertionGoldenPartition,
    AssertionGoldenSuite,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    EvidenceSourceKind,
    StandardReference,
    TextBlock,
)

TEXT = "A verification activity is described."


def _document() -> EngineeringDocument:
    return EngineeringDocument(
        key=DocumentKey(value="TEST"),
        title="Synthetic",
        document_type=DocumentType.STANDARD,
        clauses=(
            Clause(
                id=ClauseId(value="c1"),
                reference=StandardReference(standard="TEST", clause="1"),
                clause_type=ClauseType.CLAUSE,
                content=(TextBlock(id="t1", text=TEXT),),
            ),
        ),
    )


def _suite() -> AssertionGoldenSuite:
    return AssertionGoldenSuite(
        id="dev",
        version="1.0.0",
        partition=AssertionGoldenPartition.DEVELOPMENT,
        audit=AssertionAuditBinding(review_id="r", review_version="1", audit_sha256="a" * 64),
        ontology_versions=("standards-atlas-core@2.0.0",),
        cases=(
            AssertionGoldenCase(
                source_document_key="TEST",
                clause_id=ClauseId(value="c1"),
                reference="TEST:1",
                canonical_reference="TEST 1",
                text_sha256=hashlib.sha256(TEXT.encode()).hexdigest(),
                source_sha256="b" * 64,
                entities=(),
                assertions=(),
            ),
        ),
    )


def _scope(tmp_path: Path):
    workspace = tmp_path / ".atlas" / "data"
    source_repo = FileSystemContextSourcePackageRepository(workspace)
    manifest = plan_assertion_experiment(
        _suite(),
        {"TEST": _document()},
        experiment_id="exp-1",
        code_revision="sha256:" + "c" * 64,
        variant_id="B0",
        prompt_version="ontology-guided-assertions-source-bound-v1",
        model_route="fake",
        source_packages=source_repo,
        budget=ExperimentBudget(max_calls=1),
        requested_model="fake",
        execution_authorized=True,
        authorization_reference="human-approved-synthetic-plan",
    )
    FileSystemAssertionExperimentRepository(tmp_path, workspace).save_manifest(manifest)

    review_workspace = tmp_path / "local" / "review" / "assertions" / "ap03"
    surface = AssertionReviewSurface(
        source_ref="target-body",
        source_clause_id="c1",
        source_kind=EvidenceSourceKind.BODY,
        label="target",
        text=TEXT,
        start_offset=0,
        content_hash="sha256:" + hashlib.sha256(TEXT.encode()).hexdigest(),
    )
    package = package_from_cases(
        id="ap03",
        version="1",
        corpus_plan_sha256="d" * 64,
        ontology_versions=("standards-atlas-core@2.0.0",),
        class_options=(ReviewOntologyOption(iri="https://example.test/WP", label="WP"),),
        predicate_options=(ReviewOntologyOption(iri="https://example.test/requires", label="req"),),
        cases=(
            AssertionReviewWorkbenchCase(
                case_id="TEST:c1",
                document_key="TEST",
                clause_id="c1",
                reference="TEST:1",
                partition=AssertionGoldenPartition.DEVELOPMENT,
                source_group="dev-group",
                source_package_sha256=manifest.cases[0].source_package_sha256,
                surfaces=(surface,),
            ),
        ),
    )
    write_assertion_review_package(review_workspace / "assertions", package)
    config = McpServerConfig.model_validate(
        {
            "profile": "ap03-development",
            "workspace": str(workspace),
            "allowed_document_keys": ["TEST"],
            "review": {"enabled": True, "workspace": str(review_workspace)},
            "ap03_development": {
                "review_handles": ["assertions"],
                "experiment_ids": ["exp-1"],
                "project_root": str(tmp_path),
                "allowed_data_routes": ["local-private-context-source-packages"],
            },
        }
    )
    return McpDevelopmentScope(config), manifest


def _proposal(manifest):
    return {
        "request_id": "request-1",
        "base_experiment_id": "exp-1",
        "base_manifest_sha256": manifest_sha256(manifest),
        "base_prompt_task": "formal-semantic-knowledge-proposal",
        "base_prompt_version": manifest.prompt_version,
        "proposed_prompt_version": "codex-small-fix-1",
        "proposed_variant_id": "P3-codex",
        "hypothesis": "Make one Development-only role instruction more explicit.",
        "error_clusters": [
            {"code": "missing_work_product", "summary": "Synthetic cluster", "case_ids": ["c1"]}
        ],
        "data_route": manifest.data_route,
        "change": {
            "kind": "replace_role_system_prompt",
            "system_prompt": (
                "Extract source-bound engineering entities and assertions. "
                "Keep work products explicit."
            ),
        },
    }


def test_codex_proposal_stages_only_a_bound_prompt_variant(tmp_path: Path) -> None:
    scope, manifest = _scope(tmp_path)
    service = McpCodexOptimizationService(scope)

    receipt = service.submit_prompt_variant_proposal(_proposal(manifest))
    repeated = service.submit_prompt_variant_proposal(_proposal(manifest))

    assert repeated == receipt
    assert receipt["execution_performed"] is False
    assert receipt["inherited_partition"] == "development"
    assert receipt["inherited_data_route"] == manifest.data_route
    assert receipt["inherited_budget"] == {
        "max_calls": 1,
        "max_retries_per_case": 0,
        "max_total_tokens": None,
        "max_total_tokens_per_call": None,
        "max_runtime_seconds": None,
    }
    root = tmp_path / receipt["staged_bundle_relative_path"]
    assert root.is_dir()
    assert (root / "staging-receipt.json").is_file()
    metadata = json.loads((root / "prompt.json").read_text())
    assert metadata["qualification_status"] == "unqualified-development"
    assert metadata["variant_id"] == "P3-codex"
    assert "Keep work products explicit" in (root / "system.txt").read_text()


def test_codex_proposal_cannot_add_plan_or_golden_controls(tmp_path: Path) -> None:
    _, manifest = _scope(tmp_path)
    payload = _proposal(manifest)
    payload["max_calls"] = 99
    with pytest.raises(ValueError, match="Extra inputs"):
        CodexOptimizationProposal.model_validate(payload)


def test_codex_proposal_rejects_stale_plan_and_foreign_case(tmp_path: Path) -> None:
    scope, manifest = _scope(tmp_path)
    service = McpCodexOptimizationService(scope)
    stale = _proposal(manifest)
    stale["base_manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="stale"):
        service.submit_prompt_variant_proposal(stale)

    foreign = _proposal(manifest)
    foreign["request_id"] = "request-2"
    foreign["proposed_prompt_version"] = "codex-small-fix-2"
    foreign["error_clusters"][0]["case_ids"] = ["holdout-case"]
    with pytest.raises(ValueError, match="outside the base plan"):
        service.submit_prompt_variant_proposal(foreign)
