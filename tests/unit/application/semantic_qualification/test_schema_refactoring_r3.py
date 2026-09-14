"""R3: current-only contracts at models, repositories and archive boundaries.

All sources and decisions are synthetic. An old checksum is not a license to
upgrade a payload, infer missing observations or overwrite human authority.
"""

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml
from pydantic import TypeAdapter
from test_partial_observations import RESOURCES
from test_qualification_campaign import source_files
from test_review_package import make_review
from test_review_preparation import consensus_history

from standards_atlas.adapters.evaluation import EngineeringDocumentClauseProvider
from standards_atlas.adapters.evaluation.qualification_knowledge_source import _Archive
from standards_atlas.adapters.filesystem import FileSystemEngineeringDocumentRepository
from standards_atlas.adapters.filesystem.document_repository import _document_from_payload
from standards_atlas.adapters.mcp import McpClauseService, McpServerConfig
from standards_atlas.adapters.workflow import FileSystemWorkflowArtifactStore
from standards_atlas.application.model.knowledge_adoption import (
    ClauseKnowledgeCandidate,
    KnowledgeAdoptionBatch,
)
from standards_atlas.application.schema import SCHEMA_POLICIES, SchemaPolicy
from standards_atlas.application.semantic_qualification import analysis_archive
from standards_atlas.application.semantic_qualification.artifact_contracts import (
    validate_qualification_artifact,
)
from standards_atlas.application.semantic_qualification.campaign_selection import prepare_campaign
from standards_atlas.application.semantic_qualification.cascade_provenance import (
    validate_cascade_provenance,
)
from standards_atlas.application.semantic_qualification.cascade_replay_source import (
    CascadeReplaySource,
)
from standards_atlas.application.semantic_qualification.challenger import (
    _has_applicability_disagreement,
    write_challenger_manifest,
)
from standards_atlas.application.semantic_qualification.consensus import (
    ConsensusReport,
    _write_outputs,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    ModelPromptQualificationService,
    QualificationMatrixManifest,
    QualificationMatrixReport,
)
from standards_atlas.application.semantic_qualification.review_package.candidates import (
    build_candidate_index,
    load_candidate_index,
)
from standards_atlas.application.semantic_qualification.semantic_extraction_run_provenance import (
    _cascade_context_sha256,
)
from standards_atlas.application.services.knowledge_adoption_service import KnowledgeAdoptionService
from standards_atlas.application.workflow.manifest_registry import WorkflowManifestLoader
from standards_atlas.application.workflow.models import (
    ArtifactPolicy,
    WorkflowOperation,
    WorkflowOperationKind,
    WorkflowStage,
    WorkflowStep,
)
from standards_atlas.domain.model import (
    Clause,
    ClauseId,
    ClauseType,
    DocumentKey,
    DocumentType,
    EngineeringDocument,
    GeneratedAttribute,
    GenerationMethod,
    StandardReference,
    TextBlock,
)
from standards_atlas.domain.model.enrichment_patch import (
    ClauseEnrichmentPatch,
    SemanticEnrichmentPatch,
)

pytestmark = pytest.mark.filterwarnings(
    "error::standards_atlas.application.schema.policy.SchemaDeprecationWarning"
)

FAMILIES = {
    "cascade-provenance": "1.6",
    "qualification-matrix-report": "1.1",
    "qualification-consensus": "5.0",
    "engineering-document": 9,
    "knowledge-adoption-batch": "1.1",
    "qualification-matrix-manifest": "1.6",
}
MODELS = {
    "qualification-matrix-report": QualificationMatrixReport,
    "qualification-consensus": ConsensusReport,
    "knowledge-adoption-batch": KnowledgeAdoptionBatch,
    "qualification-matrix-manifest": QualificationMatrixManifest,
}
OLD = {
    "cascade-provenance": "1.5",
    "qualification-matrix-report": "1.0",
    "qualification-consensus": "4.0",
    "engineering-document": 8,
    "knowledge-adoption-batch": "1.0",
    "qualification-matrix-manifest": "1.5",
}
NAMES = {
    "cascade-provenance": "cascade-provenance.json",
    "qualification-matrix-report": "qualification-matrix.json",
    "qualification-consensus": "nested/consensus-report.json",
    "knowledge-adoption-batch": "knowledge-adoption-batch.json",
    "qualification-matrix-manifest": "configuration/qualification-manifest.yaml",
}
NOW = datetime(2026, 9, 14, tzinfo=UTC)


def payload(family):
    data = {"schema_version": FAMILIES[family]}
    if family == "qualification-matrix-manifest":
        data.update(
            matrix_id="r3",
            corpus_id="r3-corpus",
            prompts=[{"id": "p"}],
            models=[{"id": "m", "provider": "test"}],
        )
    elif family == "qualification-matrix-report":
        data.update(
            matrix_id="r3",
            corpus_id="r3-corpus",
            generated_at=NOW.isoformat(),
            passed=False,
            ranking=[],
            pareto_front=[],
            candidates=[],
        )
    elif family == "qualification-consensus":
        data.update(
            matrix_id="r3",
            corpus_id="r3-corpus",
            generated_at=NOW.isoformat(),
            prompt_id="p",
            reasoning_mode_id="disabled",
            model_count=0,
            clause_count=0,
            categories={},
            review_count=0,
            clauses=[],
        )
    elif family == "knowledge-adoption-batch":
        data.update(
            source_id="synthetic",
            source_sha256="a" * 64,
            selected_clause_count=0,
            unqualified_clause_count=0,
            candidates=[],
        )
    elif family == "cascade-provenance":
        data.update(matrix_id="r3", stages=[])
    elif family == "engineering-document":
        data["document"] = document().model_dump(mode="json")
    return data


def document():
    return EngineeringDocument(
        key=DocumentKey(value="R3"),
        title="R3 synthetic",
        document_type=DocumentType.OTHER,
        clauses=(
            Clause(
                id=ClauseId(value="c"),
                reference=StandardReference(standard="R3", clause="1"),
                clause_type=ClauseType.CLAUSE,
                content=(TextBlock(id="t", text="Synthetic."),),
            ),
        ),
    )


def hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize("family", FAMILIES)
def test_r3_reader_and_writer_policies_are_current_only(family):
    policy = SCHEMA_POLICIES[family]
    assert policy.current == FAMILIES[family]
    assert policy.readable == (policy.current,)
    assert policy.deprecated == ()
    for check in (policy.require_readable, policy.require_current_for_write):
        check(FAMILIES[family])
        with pytest.raises(ValueError):
            check(OLD[family])


@pytest.mark.parametrize("family", MODELS)
def test_r3_models_require_explicit_markers_and_roundtrip(family):
    model = MODELS[family]
    contract = model.model_json_schema()
    assert "schema_version" in contract["required"]
    assert contract["properties"]["schema_version"]["const"] == FAMILIES[family]
    original = model.model_validate(payload(family))
    assert model.model_validate_json(original.model_dump_json()) == original


@pytest.mark.parametrize("family", MODELS)
@pytest.mark.parametrize("wire", ("mapping", "json", "copy", "nested"))
@pytest.mark.parametrize("bad", ("old", "missing", None, True, 1.1, "99.0"))
def test_r3_model_boundaries_reject_invalid_versions(family, wire, bad):
    data = payload(family)
    marker = OLD[family] if bad == "old" else bad
    if bad == "missing":
        del data["schema_version"]
    else:
        data["schema_version"] = marker
    model = MODELS[family]
    with pytest.raises(ValueError, match="schema_version"):
        if wire == "mapping":
            model.model_validate(data)
        elif wire == "json":
            model.model_validate_json(json.dumps(data))
        else:
            unchecked = model.model_construct(**data)
            if wire == "nested":
                TypeAdapter(tuple[model, ...]).validate_python((unchecked,))
            else:
                model.model_validate(unchecked)


@pytest.mark.parametrize("bad", ("old", "missing", None, True, 9.0, "9", 99))
@pytest.mark.parametrize("reader", ("direct", "load", "list", "list_readable", "mcp"))
def test_document_envelopes_are_not_upgraded_or_silently_hidden(tmp_path, bad, reader):
    data = payload("engineering-document")
    if bad == "missing":
        del data["schema_version"]
    else:
        data["schema_version"] = 8 if bad == "old" else bad
    path = tmp_path / "documents/R3.json"
    path.parent.mkdir()
    path.write_text(json.dumps(data))
    before = hashes(tmp_path)
    repo = FileSystemEngineeringDocumentRepository(tmp_path)
    with pytest.raises(ValueError, match="schema.version"):
        if reader == "direct":
            _document_from_payload(data)
        elif reader == "load":
            repo.load(DocumentKey(value="R3"))
        elif reader == "mcp":
            service = McpClauseService(
                EngineeringDocumentClauseProvider(tmp_path), McpServerConfig(workspace=tmp_path)
            )
            service.list_documents()
        else:
            getattr(repo, reader)()
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("bad", ("1.5", "missing", None, 1.6, True, "99.0"))
def test_provenance_envelope_rejection_is_non_mutating(bad):
    data = payload("cascade-provenance")
    if bad == "missing":
        data.pop("schema_version")
    else:
        data["schema_version"] = bad
    before = copy.deepcopy(data)
    with pytest.raises(ValueError, match="schema version"):
        validate_cascade_provenance(data)
    assert data == before


@pytest.mark.parametrize("family", NAMES)
@pytest.mark.parametrize("kind", ("directory", "zip", "verified-archive"))
def test_embedded_obsolete_contracts_are_rejected_even_with_valid_checksums(tmp_path, family, kind):
    data = payload(family)
    data["schema_version"] = OLD[family]
    name = NAMES[family]
    raw = json.dumps(data).encode()  # JSON is a valid YAML mapping as well.
    source = tmp_path / "source"
    source.mkdir()
    entry = {"path": name, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if kind == "directory":
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        reader = CascadeReplaySource(source)
    else:
        archive = tmp_path / "source.zip"
        with ZipFile(archive, "w") as zipped:
            zipped.writestr(name, raw)
            zipped.writestr(
                "archive-manifest.json",
                json.dumps(
                    {
                        "archive_id": "synthetic-r3",
                        "files": [entry],
                    }
                ),
            )
        reader = _Archive(archive) if kind == "verified-archive" else CascadeReplaySource(archive)
    before = hashes(tmp_path)
    try:
        with pytest.raises(ValueError, match="invalid qualification artifact"):
            reader.read(name)
    finally:
        reader.close()
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("family", NAMES)
def test_recognized_current_artifacts_preserve_exact_bytes(tmp_path, family):
    name = NAMES[family]
    raw = json.dumps(payload(family), indent=3).encode()
    validate_qualification_artifact(name, raw)
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    reader = CascadeReplaySource(tmp_path)
    try:
        assert reader.read(name) == raw
    finally:
        reader.close()
    assert path.read_bytes() == raw


@pytest.mark.parametrize("family", NAMES)
def test_archive_creation_refuses_obsolete_member_before_publishing(tmp_path, family):
    manifest = tmp_path / "matrix.yaml"
    manifest.write_text(yaml.safe_dump(payload("qualification-matrix-manifest")))
    bad = payload(family)
    bad["schema_version"] = OLD[family]
    member = tmp_path / "source.json"
    member.write_text(json.dumps(bad))
    before = member.read_bytes()
    output = tmp_path / "archives"
    with pytest.raises(ValueError, match="invalid qualification artifact"):
        analysis_archive.create_analysis_archive(
            output_directory=tmp_path / "work",
            matrix_id="r3",
            manifest_path=manifest,
            core_paths=(),
            input_members=((member, NAMES[family]),),
            archive_directory=output,
        )
    assert not list(output.glob("*.zip"))
    assert not (output / "qualification-run-index.json").exists()
    assert member.read_bytes() == before


def test_provenance_fingerprint_input_is_not_default_filled(tmp_path):
    data = payload("cascade-provenance")
    data["stages"] = [{"stage_id": "s"}]
    assert validate_cascade_provenance(data) is data
    (tmp_path / "cascade-provenance.json").write_text(json.dumps(data))
    path = tmp_path / "cascade/s/consensus-report.json"
    path.parent.mkdir(parents=True)
    report = payload("qualification-consensus")
    path.write_text(json.dumps(report))
    before = hashes(tmp_path)
    digest = _cascade_context_sha256(tmp_path)
    assert digest == _cascade_context_sha256(tmp_path)
    assert hashes(tmp_path) == before
    report["schema_version"] = "4.0"
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="schema_version"):
        _cascade_context_sha256(tmp_path)


@pytest.mark.parametrize("wire", ("file", "zip"))
def test_review_history_rejects_obsolete_reports_without_an_index_or_membership_change(
    tmp_path,
    wire,
):
    root, _, items, _ = make_review(tmp_path / "review")
    path = tmp_path / "consensus-report.json"
    data = consensus_history(path, items[0])
    data["schema_version"] = "4.0"
    path.write_text(json.dumps(data))
    if wire == "zip":
        archive = tmp_path / "history.zip"
        with ZipFile(archive, "w") as zipped:
            zipped.writestr("nested/consensus-report.json", path.read_bytes())
        path = archive
    before = hashes(root)
    with pytest.raises(ValueError, match="schema_version"):
        build_candidate_index(root, histories=(path,))
    assert hashes(root) == before


def test_current_historical_null_empty_and_missing_votes_remain_distinct(tmp_path):
    root, _, items, _ = make_review(tmp_path / "review")
    path = tmp_path / "consensus-report.json"
    data = consensus_history(
        path,
        items[0],
        votes=[
            {
                "model_id": "model",
                "repetitions": 1,
                "stability": 1,
                "process_functions": [],
                "process_primary_evaluated": True,
                "primary_process_function": None,
            }
        ],
        process_set_evaluated=True,
        process_primary_evaluated=True,
        process_set_category="unanimous",
        process_primary_category="unanimous",
        proposed_process_functions=[],
        primary_process_function=None,
    )
    raw = path.read_bytes()
    result = build_candidate_index(root, histories=(path,))
    _, _, index = load_candidate_index(root, result["index_sha256"])
    row = next(e for e in index.entries if e.example_id == items[0].id)
    signals = {s.attribute: s for s in row.history if s.artifact_kind == "consensus"}
    assert signals["process_functions"].model_values == {"model": []}
    assert signals["primary_process_function"].model_values == {"model": None}
    assert signals["role_semantics_present"].model_values == {}
    assert signals["role_semantics_present"].predicate is None
    assert path.read_bytes() == raw
    assert "applicability_present" not in data["clauses"][0]["votes"][0]


def test_challenger_does_not_turn_a_missing_vote_into_a_negative():
    assert not _has_applicability_disagreement([{}, {"applicability_present": True}])
    assert _has_applicability_disagreement(
        [
            {"applicability_present": False},
            {"applicability_present": True},
        ]
    )
    assert not _has_applicability_disagreement(
        [
            {"applicability_present": False, "applicability_presence_eligible": False},
            {"applicability_present": True},
        ]
    )


def test_consensus_writer_rejects_unchecked_old_copy_before_overwrite(tmp_path):
    report = ConsensusReport.model_validate(payload("qualification-consensus"))
    _write_outputs(report, tmp_path)
    before = hashes(tmp_path)
    with pytest.raises(ValueError, match="schema_version"):
        _write_outputs(report.model_copy(update={"schema_version": "4.0"}), tmp_path)
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("family", FAMILIES)
def test_real_writers_enforce_registry_current_before_output(tmp_path, monkeypatch, family):
    old_policy = SCHEMA_POLICIES[family]
    next_version = 10 if family == "engineering-document" else "99.0"
    monkeypatch.setitem(
        SCHEMA_POLICIES,
        family,
        SchemaPolicy(
            family,
            next_version,
            (next_version,),
            old_policy.location,
        ),
    )
    target = tmp_path / "output"
    # R4 may reject already at model input, before a writer can emit anything.
    with pytest.raises(ValueError, match="writers may only emit|Unsupported .* schema version"):
        if family == "cascade-provenance":
            manifest = tmp_path / "matrix.yaml"
            manifest.write_text(yaml.safe_dump(payload("qualification-matrix-manifest")))
            analysis_archive.write_cascade_provenance(
                output_directory=target,
                matrix_id="r3",
                manifest_path=manifest,
                run_mode="cascade",
                stages=[],
            )
        elif family == "qualification-consensus":
            _write_outputs(ConsensusReport.model_validate(payload(family)), target)
        elif family == "qualification-matrix-report":
            ModelPromptQualificationService().evaluate(
                QualificationMatrixManifest.model_validate(
                    payload("qualification-matrix-manifest")
                ),
                target,
            )
        elif family == "qualification-matrix-manifest":
            manifest = QualificationMatrixManifest.load(
                Path(
                    "manifests/multidimensional-semantic-qualification-v3-semantic-profile-v1.yaml"
                )
            )
            write_challenger_manifest(manifest=manifest, path=target / "matrix.yaml")
        elif family == "knowledge-adoption-batch":
            KnowledgeAdoptionService(
                documents=FileSystemEngineeringDocumentRepository(target)
            ).apply(KnowledgeAdoptionBatch.model_validate(payload(family)), write=True)
        else:
            FileSystemEngineeringDocumentRepository(target).save(document())
    assert not [p for p in target.rglob("*") if p.is_file()]


def test_manifest_loader_registry_and_campaign_freeze_reject_obsolete_input(tmp_path):
    path, _, _ = source_files(tmp_path / "source")
    matrix = path.parent / "matrix.yaml"
    data = yaml.safe_load(matrix.read_text())
    data["schema_version"] = "1.5"
    matrix.write_text(yaml.safe_dump(data))
    before = hashes(tmp_path)
    with pytest.raises(ValueError, match="schema_version"):
        QualificationMatrixManifest.load(matrix)
    with pytest.raises(ValueError, match="schema version"):
        WorkflowManifestLoader().load((matrix,))
    with pytest.raises(ValueError, match="schema_version"):
        prepare_campaign(manifest=path, output=tmp_path / "campaign", resources=RESOURCES)
    assert hashes(tmp_path) == before


def test_empty_source_requirements_are_explicit_and_adoption_keeps_confirmed_values(tmp_path):
    from standards_atlas.application.semantic_qualification.annotations import (
        normalized_content_hash,
    )

    repo = FileSystemEngineeringDocumentRepository(tmp_path)
    doc = document()
    clause = doc.clauses[0].confirm_authoritative(
        "enrichments.semantic.applicability_present", authority="synthetic-review"
    )
    doc = doc.model_copy(update={"clauses": (clause,)})
    repo.save(doc)
    candidate = ClauseKnowledgeCandidate(
        document_key="R3",
        clause_id="c",
        reference="1",
        content_hash=normalized_content_hash(clause.plain_text),
        patch=ClauseEnrichmentPatch(semantic=SemanticEnrichmentPatch(applicability_present=True)),
        attributes=(
            GeneratedAttribute(
                path="enrichments.semantic.applicability_present",
                generator="r3",
                method=GenerationMethod.IMPORTED,
            ),
        ),
    )
    batch = KnowledgeAdoptionBatch.model_validate(
        {
            **payload("knowledge-adoption-batch"),
            "selected_clause_count": 1,
            "candidates": [candidate],
        }
    )
    encoded = batch.model_dump(mode="json")
    assert encoded["candidates"][0]["source_requirements"] == []
    assert KnowledgeAdoptionBatch.model_validate_json(batch.model_dump_json()) == batch
    before = hashes(tmp_path)
    service = KnowledgeAdoptionService(documents=repo)
    result = service.apply(batch, write=True)
    assert not result.written_document_keys
    assert hashes(tmp_path) == before
    with pytest.raises(ValueError, match="schema_version"):
        service.apply(batch.model_copy(update={"schema_version": "1.0"}), write=True)
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("version", (8, 9.0, "9", None))
@pytest.mark.parametrize("stage", (WorkflowStage.CORPUS_BUILD, WorkflowStage.CONTEXT_ENRICHMENT))
def test_obsolete_document_cannot_be_checkpointed_or_reused(tmp_path, version, stage):
    repo = FileSystemEngineeringDocumentRepository(tmp_path / ".atlas/data")
    repo.save(document())
    operation = (
        WorkflowOperation.create(WorkflowOperationKind.EVALUATION_CORPUS_BUILD, documents=("R3",))
        if stage is WorkflowStage.CORPUS_BUILD
        else WorkflowOperation.create(WorkflowOperationKind.DOCUMENT_ENRICH_CONTEXT, document="R3")
    )
    step = WorkflowStep(
        family="R3",
        document="R3",
        stage=stage,
        operation=operation,
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(".atlas/work/workflow/r3.complete",),
    )
    store = FileSystemWorkflowArtifactStore()
    store.record_completion(step, tmp_path)
    assert store.outputs_exist(step, tmp_path)
    path = tmp_path / ".atlas/data/documents/R3.json"
    data = json.loads(path.read_text())
    if version is None:
        data.pop("schema_version")
    else:
        data["schema_version"] = version
    path.write_text(json.dumps(data))
    before = hashes(tmp_path)
    for operation in (store.outputs_exist, store.record_completion):
        with pytest.raises(ValueError, match="schema"):
            operation(step, tmp_path)
    assert hashes(tmp_path) == before


@pytest.mark.parametrize("version", (8, 9.0, "9", None))
def test_workflow_output_cannot_coerce_a_document_schema_marker(tmp_path, version):
    relative = ".atlas/data/documents/R3.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema_version": version, "document": {}}))
    step = WorkflowStep(
        family="R3",
        document="R3",
        stage=WorkflowStage.IMPORT,
        operation=WorkflowOperation.create(WorkflowOperationKind.DOCUMENT_IMPORT, source="unused"),
        artifact_policy=ArtifactPolicy.DERIVED,
        output_paths=(relative,),
    )
    assert not FileSystemWorkflowArtifactStore().outputs_exist(step, tmp_path)


def test_archive_rejects_conflicting_current_inputs_with_the_same_member_name(tmp_path):
    manifest = tmp_path / "matrix.yaml"
    manifest.write_text(yaml.safe_dump(payload("qualification-matrix-manifest")))
    other = tmp_path / "other.yaml"
    other.write_text(
        yaml.safe_dump(
            {
                **payload("qualification-matrix-manifest"),
                "matrix_id": "different",
            }
        )
    )
    output = tmp_path / "archives"
    with pytest.raises(ValueError, match="conflicting qualification archive member"):
        analysis_archive.create_analysis_archive(
            output_directory=tmp_path / "work",
            matrix_id="r3",
            manifest_path=manifest,
            core_paths=(),
            input_members=((other, "configuration/qualification-manifest.yaml"),),
            archive_directory=output,
        )
    assert not list(output.glob("*.zip"))
