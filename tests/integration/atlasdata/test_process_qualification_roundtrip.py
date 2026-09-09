"""Fresh deterministic gateway responses through qualification, archive and AtlasData.

No external provider, source documents, or historical qualification labels are
needed. The third clause intentionally omits fields that normalization defaults.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import yaml

from standards_atlas.adapters.atlasdata.knowledge_transfer import AtlasDataKnowledgeService
from standards_atlas.adapters.evaluation.qualification_knowledge_source import (
    load_qualification_knowledge,
)
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.application.catalog.atlasdata_binding import atlasdata_bindings
from standards_atlas.application.catalog.models import StandardCatalog
from standards_atlas.application.context.canonical_cbox import project_clause_enrichments
from standards_atlas.application.evaluation.models import EvaluationDataset, EvaluationExample
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.application.semantic_qualification.analysis_archive import (
    build_analysis_metrics,
)
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
from standards_atlas.application.semantic_qualification.consensus import ModelConsensusService
from standards_atlas.application.semantic_qualification.proposals import (
    BaselineProposalGenerator,
    ProposalRunConfig,
)
from standards_atlas.application.semantic_qualification.qualification_coverage import (
    build_qualification_coverage,
)
from standards_atlas.application.semantic_qualification.run_selection import (
    QualificationRunSelection,
    QualificationSelectionClause,
)
from standards_atlas.application.services.knowledge_adoption_service import KnowledgeAdoptionService
from standards_atlas.domain.model import TextBlock
from standards_atlas.domain.model.enrichment_patch import (
    ClauseEnrichmentPatch,
    SemanticEnrichmentPatch,
    merge_generated_enrichments,
)
from standards_atlas.domain.model.knowledge_state import GeneratedAttribute, GenerationMethod
from standards_atlas.shared.hashing import sha256_bytes, sha256_json

S = "enrichments.semantic."
TASK = "semantic-profile-classification"
PROMPT = "structure-aware-v10"
NOW = datetime(2026, 9, 9, tzinfo=UTC)


class ProcessGateway:
    """Generate different complete, negative, and absent structured observations."""

    def __init__(self):
        self.calls = 0

    def generate_structured(self, request):
        self.calls += 1
        reference = request.metadata["clause_context"]["reference"]
        value = {
            "statement_functions": ["requirement"],
            "primary_function": "requirement",
            "knowledge_kinds": ["process"],
            "primary_knowledge_kind": "process",
            "applicability_present": False,
            "role_semantics_present": False,
            "role_relations": [],
            "confidence": 0.9,
            "rationale": "Synthetic only. Prose suggesting output is not structured evidence.",
        }
        if reference.endswith("1"):
            value.update(
                process_functions=["activity", "input"], primary_process_function="activity"
            )
            if request.model == "model-c":
                value["process_functions"] = ["activity", "output"]
        elif reference.endswith("2"):
            value.update(process_functions=[], primary_process_function=None)
        return StructuredGenerationResult(
            value=value,
            model=request.model,
            provider="fake",
            prompt_version=request.prompt_version,
            input_hash=sha256_json(asdict(request)),
            raw_response_hash=sha256_json(value),
            duration_ms=1,
            raw_response={"synthetic": True},
        )


def world(root):
    public = root / "data"
    public.mkdir()
    (public / "EXAMPLE").write_text(
        'name="Example"\ndigits=4\nlifecycle_status="published"\n'
        'semanticProfile="functional-safety:1.0.0"\n'
        'structure=(\n "2025 r1 r2 r3"\n)\n#---data---#\n'
        "TOC;aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa;Example:2025 1;One;r\n"
        "TOC;bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb;Example:2025 2;Two;r\n"
        "TOC;cccccccccccccccccccccccccccccccc;Example:2025 3;Three;r\n"
    )
    catalog = StandardCatalog.model_validate(
        {
            "manifest_type": "standards",
            "schema_version": 2,
            "knowledge_domains": [],
            "industry_sectors": [],
            "families": [
                {
                    "key": "EXAMPLE",
                    "name": "Example",
                    "organization": "Example",
                    "publication_year": 2025,
                    "source": {"pdf": "local/example.pdf"},
                    "atlasdata": {"path": "data/EXAMPLE"},
                }
            ],
        }
    )
    bindings = atlasdata_bindings(catalog, root=root)
    repo = FileSystemEngineeringDocumentRepository(root / "workspace")
    service = AtlasDataKnowledgeService(
        documents=repo, bindings=bindings, evidence_root=root / "private-evidence"
    )
    doc = service._skeleton(bindings["EXAMPLE"])
    doc = doc.model_copy(
        update={
            "clauses": tuple(
                clause.with_baseline_updates(
                    content=(
                        TextBlock(
                            id=f"text-{i}",
                            text=f"Synthetic source clause {i} shall remain local.",
                        ),
                    )
                )
                for i, clause in enumerate(doc.clauses, 1)
            )
        }
    )
    repo.save(doc)
    return repo, service, bindings, doc


def qualification(root, document):
    examples = tuple(
        EvaluationExample(
            id=c.id.value,
            input={
                "content": {"text": c.plain_text, "hash": normalized_content_hash(c.plain_text)},
                "context": {
                    "knowledge_domain": "functional-safety",
                    "document_key": "EXAMPLE",
                    "clause_id": c.id.value,
                    "reference": c.reference.clause,
                    "heading": c.heading,
                    "clause_type": "clause",
                },
            },
            expected={},
        )
        for c in document.clauses
    )
    dataset = EvaluationDataset(task=TASK, version="synthetic", examples=examples)
    corpus = EvaluationCorpusManifest(
        corpus_id="process-synthetic",
        task=TASK,
        corpus_version="synthetic",
        seed=1,
        selection_strategy="synthetic",
        clauses=tuple(
            CorpusClause(
                clause=ClauseReference(
                    knowledge_domain="functional-safety",
                    document_key="EXAMPLE",
                    clause_id=e.id,
                    content_hash=e.input["content"]["hash"],
                )
            )
            for e in examples
        ),
    )
    corpus_root = root / "corpora"
    directory = corpus_root / TASK / dataset.version
    directory.mkdir(parents=True)
    (directory / "dataset.json").write_text(json.dumps(asdict(dataset)))
    (directory / "corpus.yaml").write_text(yaml.safe_dump(corpus.model_dump(mode="json")))
    gateway = ProcessGateway()
    generator = BaselineProposalGenerator(gateway)
    observations = []
    for model in ("model-a", "model-b", "model-c"):
        config = ProposalRunConfig(
            corpus_id=corpus.corpus_id,
            task=TASK,
            task_version="2.5.0",
            dataset_version=dataset.version,
            prompt_version=PROMPT,
            provider="fake",
            model=model,
            retry_attempts=1,
        )
        kwargs = dict(
            resources=Path("src/standards_atlas/resources/semantic"),
            corpus_root=corpus_root,
            output_root=root / "evaluation",
        )
        generated = generator.run(config, **kwargs)
        assert generated.failed == 0, generated.errors
        assert generated.generated == 3
        resumed = generator.run(config, **kwargs)
        assert resumed.skipped == 3 and resumed.generated == 0
        observations.append(
            SimpleNamespace(
                model_id=model,
                prompt_id=PROMPT,
                reasoning_mode_id="off",
                run_directory=generated.run_directory,
            )
        )
    report, *paths = ModelConsensusService().evaluate(
        matrix_id="synthetic-matrix",
        corpus_id=corpus.corpus_id,
        prompt_id=PROMPT,
        reasoning_mode_id="off",
        observations=tuple(observations),
        min_models=3,
        corpus_root=corpus_root,
        output_directory=root / "consensus",
    )
    assert gateway.calls == 9
    return dataset, corpus, report, paths


def archive(root, dataset, corpus, report):
    selection = QualificationRunSelection(
        task=dataset.task,
        dataset_version=dataset.version,
        corpus_id=corpus.corpus_id,
        dataset_sha256=sha256_json(asdict(dataset)),
        corpus_sha256=sha256_json(corpus.model_dump(mode="json")),
        dataset_clause_count=3,
        corpus_clause_count=3,
        selected_clause_count=3,
        clauses=tuple(
            QualificationSelectionClause(example_id=e.id, document_key="EXAMPLE", clause_id=e.id)
            for e in dataset.examples
        ),
    )
    coverage = build_qualification_coverage(selection=selection, report=report)
    detail = build_applicability_detail_selection(
        run_selection=selection,
        examples=dataset.examples,
        consensus=report,
        coverage=coverage,
        task_version="2.5.0",
    )
    policy = ApplicabilityPolicyRunReport(
        generated_at=NOW,
        source_matrix_id=report.matrix_id,
        source_corpus_id=corpus.corpus_id,
        source_selection_sha256=detail.fingerprint,
        source_consensus_sha256=detail.source_consensus_sha256,
        consensus_clause_count=3,
        selected_clause_count=0,
        final_positive_count=0,
        final_negative_count=3,
        final_unknown_count=0,
        cases=tuple(
            ApplicabilityPolicyRunCase(
                document_key="EXAMPLE",
                clause_id=c.clause_id,
                reference=c.reference,
                gate_present=False,
                detail_selected=False,
                final_present=False,
            )
            for c in report.clauses
        ),
        stages=tuple(
            ApplicabilityPolicyStageSummary(
                role=role,
                task_version="2.0.0",
                prompt_version="synthetic",
                model_id="not-called",
                model_ref="not-called",
                selection_sha256=detail.fingerprint,
                selected_clause_count=0,
                pending_clause_count=0,
                attempted_clause_count=0,
                reused_clause_count=0,
                fresh_prediction_count=0,
                cached_prediction_count=0,
                failed_clause_count=0,
            )
            for role in ("primary", "rescue", "confirmation")
        ),
    )
    prefix = "inputs/applicability-policy"
    values = {
        f"{prefix}/qualification-selection.json": selection.model_dump(mode="json"),
        f"{prefix}/{selection.dataset_snapshot}": asdict(dataset),
        f"{prefix}/{selection.corpus_snapshot}": corpus.model_dump(mode="json"),
        f"{prefix}/qualification-coverage.json": coverage.model_dump(mode="json"),
        f"{prefix}/final-consensus-report.json": report.model_dump(mode="json"),
        "applicability-policy/applicability-policy-selection.json": detail.model_dump(mode="json"),
        "applicability-policy/applicability-policy-run.json": policy.model_dump(mode="json"),
    }
    members = {name: json.dumps(value).encode() for name, value in values.items()}
    manifest = {
        "archive_id": "synthetic-process",
        "files": [
            {"path": name, "sha256": sha256_bytes(data), "size_bytes": len(data)}
            for name, data in members.items()
        ],
    }
    path = root / "synthetic-process.zip"
    with ZipFile(path, "w", ZIP_DEFLATED) as zipped:
        for name, data in members.items():
            zipped.writestr(name, data)
        zipped.writestr("archive-manifest.json", json.dumps(manifest))
    return path


def test_fresh_structured_process_results_survive_the_complete_roundtrip(tmp_path):
    repo, service, bindings, doc = world(tmp_path)
    dataset, corpus, report, paths = qualification(tmp_path, doc)
    by_id = {c.clause_id: c for c in report.clauses}
    positive, empty, absent = [by_id[c.id.value] for c in doc.clauses]
    assert report.schema_version == "5.0"
    metrics = build_analysis_metrics(report=report, cascade_stages=[])
    assert metrics["process_functions"]["set_evaluated"] == 2
    assert metrics["process_functions"]["set_not_evaluated"] == 1
    assert metrics["process_functions"]["empty_set_decisions"] == 1
    assert metrics["process_functions"]["null_primary_decisions"] == 1
    assert metrics["diagnostics"]["process_functions"] == metrics["process_functions"]
    assert positive.primary_process_function == "activity"
    assert positive.proposed_process_functions == ("activity", "input")
    assert positive.process_function_support["input"] == pytest.approx(2 / 3)
    assert positive.process_primary_confidence == 1
    assert empty.process_set_decided and empty.proposed_process_functions == ()
    assert empty.process_primary_decided and empty.primary_process_function is None
    assert not absent.process_set_evaluated and not absent.process_primary_evaluated
    golden = yaml.safe_load(paths[1].read_text())
    assert golden["schema_version"] == "4.0"
    batch = load_qualification_knowledge(archive(tmp_path, dataset, corpus, report))
    adoption = KnowledgeAdoptionService(documents=repo)
    result = adoption.apply(batch, write=True)
    assert result.written_document_keys == ("EXAMPLE",)
    adopted = repo.load(doc.key)
    positive, empty, absent = adopted.clauses
    assert positive.enrichments.semantic.process_functions == ("activity", "input")
    assert positive.enrichments.semantic.primary_process_function == "activity"
    support = {a.path: a.decision for a in positive.provenance.generated_attributes}
    assert support[S + "process_functions"].valid_votes == 3
    assert support[S + "process_functions"].supporting_votes == 2
    assert support[S + "process_functions"].label_votes == {"activity": 3, "input": 2, "output": 1}
    assert support[S + "primary_process_function"].supporting_votes == 3
    assert empty.provenance.availability(S + "process_functions") == "known"
    assert empty.provenance.availability(S + "primary_process_function") == "known"
    assert empty.enrichments.semantic.process_functions == ()
    assert empty.enrichments.semantic.primary_process_function is None
    assert absent.provenance.availability(S + "process_functions") == "not_evaluated"
    assert absent.provenance.availability(S + "primary_process_function") == "not_evaluated"
    assert not adoption.apply(batch, write=True).written_document_keys
    exported = service.export(write=True)
    assert len(exported.written_targets) == 1
    public = bindings["EXAMPLE"].enrichments_path.read_bytes()
    assert b"Synthetic source clause" not in public
    restored_repo = FileSystemEngineeringDocumentRepository(tmp_path / "restored")
    restored_service = AtlasDataKnowledgeService(
        documents=restored_repo, bindings=bindings, evidence_root=tmp_path / "private-evidence"
    )
    restored_service.import_(write=True, strict_evidence=True)
    restored = restored_repo.load(doc.key)
    assert [project_clause_enrichments(c) for c in restored.clauses] == [
        project_clause_enrichments(c) for c in adopted.clauses
    ]
    assert not service.export(write=True).written_targets
    assert bindings["EXAMPLE"].enrichments_path.read_bytes() == public


def test_replacing_a_set_does_not_turn_an_unobserved_primary_into_a_null_vote(tmp_path):
    _, _, _, doc = world(tmp_path)

    def apply(clause, values, unknown=False):
        attributes = tuple(
            GeneratedAttribute(
                path=S + name,
                generator="synthetic",
                method=GenerationMethod.LLM,
            )
            for name in values
        )
        if unknown:
            attributes += (
                GeneratedAttribute(
                    path=S + "primary_process_function",
                    generator="synthetic",
                    method=GenerationMethod.LLM,
                    availability="unknown",
                ),
            )
        return merge_generated_enrichments(
            clause, ClauseEnrichmentPatch(semantic=SemanticEnrichmentPatch(**values)), attributes
        ).clause

    initial = apply(
        doc.clauses[0],
        {
            "process_functions": ("activity",),
            "primary_process_function": "activity",
        },
    )
    for unknown in (False, True):
        changed = apply(initial, {"process_functions": ("input",)}, unknown=unknown)
        assert changed.enrichments.semantic.primary_process_function is None
        assert changed.provenance.availability(S + "primary_process_function") == "unknown"
        assert changed.provenance.availability(S + "process_functions") == "known"
    negative = apply(initial, {"process_functions": (), "primary_process_function": None})
    assert negative.provenance.availability(S + "primary_process_function") == "known"
    confirmed = initial.model_copy(
        update={
            "provenance": initial.provenance.confirm_authoritative(S + "primary_process_function")
        }
    )
    protected = apply(confirmed, {"process_functions": ("input",)})
    assert protected.enrichments.semantic == initial.enrichments.semantic
