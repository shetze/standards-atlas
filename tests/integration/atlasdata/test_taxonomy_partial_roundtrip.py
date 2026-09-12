"""Source decisions and partial model values through archive, adoption and AtlasData."""

from contextlib import contextmanager
from pathlib import Path

import pytest
import test_knowledge_roundtrip

from standards_atlas.adapters.evaluation.qualification_knowledge_source import (
    load_qualification_knowledge,
)
from standards_atlas.application.context.canonical_cbox import project_clause_enrichments
from standards_atlas.application.context.source_structure import project_source_structure
from standards_atlas.application.evaluation.models import EvaluationExample
from standards_atlas.application.ports.llm_gateway import StructuredGenerationResult
from standards_atlas.application.semantic_qualification.annotations import normalized_content_hash
from standards_atlas.application.semantic_qualification.mixed_applicability import (
    run_mixed_applicability,
)
from standards_atlas.application.semantic_qualification.mixed_evidence import (
    CompletionProfile,
    MixedConsensusReport,
)
from standards_atlas.application.semantic_qualification.partial_cascade import run_partial_cascade
from standards_atlas.application.semantic_qualification.partial_cascade_archive import (
    archive_partial_cascade,
)
from standards_atlas.application.semantic_qualification.qualification_matrix import (
    QualificationMatrixManifest,
)
from standards_atlas.application.services.knowledge_adoption_service import KnowledgeAdoptionService
from standards_atlas.domain.model import ClauseType, TextBlock

# Reuse the fixture object without a same-named import shadowed by test parameters.
world = test_knowledge_roundtrip.world

RESOURCES = Path("src/standards_atlas/resources/semantic")


def setup_source(world):
    root, repo, service, binding, _ = world
    text = binding.source.read_text().replace("2025 r1 r2 r3", "2025 t1 r2 r3")
    text = text.replace("Example:2025 1;One;r", "Example:2025 1;One;t")
    binding.source.write_text(text)
    document = service._skeleton(binding)
    selected = next(c for c in document.clauses if c.clause_type == ClauseType.TERM)
    selected = selected.with_baseline_updates(
        content=(TextBlock(id="body", text="Synthetic term."),)
    )
    selected = selected.confirm_authoritative("clause_type", authority="reviewed-source")
    document = document.model_copy(
        update={"clauses": tuple(selected if c.id == selected.id else c for c in document.clauses)}
    )
    repo.save(document)
    content_hash = normalized_content_hash(selected.plain_text)
    source = project_source_structure(
        selected, document_key=document.key.value, content_hash=content_hash
    )
    example = EvaluationExample(
        id=selected.id.value,
        expected={},
        input={
            "content": {"text": selected.plain_text, "hash": content_hash},
            "context": {
                "knowledge_domain": "functional-safety",
                "document_key": document.key.value,
                "clause_id": selected.id.value,
                "reference": selected.reference.clause,
                "heading": selected.heading,
                "clause_type": "term",
                "source_structure": source.model_dump(mode="json"),
            },
        },
    )
    manifest = QualificationMatrixManifest.load(
        Path("manifests/multidimensional-semantic-qualification-v7-taxonomy-grounded-v1.yaml")
    )
    return document, selected, example, manifest


class Gateway:
    def __init__(self):
        self.calls = 0

    def generate_structured(self, request):
        self.calls += 1
        values = {
            "statement_functions": ["definition"],
            "primary_knowledge_kind": "process",
            "knowledge_kinds": ["process"],
            "primary_process_function": None,
            "process_functions": [],
            "applicability_present": False,
            "role_semantics_present": False,
            "role_relations": [],
        }
        value = {k: values[k] for k in request.output_schema["required"]}
        return StructuredGenerationResult(
            value=value,
            provider="fixture",
            model=request.model,
            prompt_version=request.prompt_version,
            input_hash="test",
            raw_response_hash="test",
            duration_ms=100,
        )


@pytest.mark.parametrize("focused", [True, False])
def test_archive_to_canonical_public_roundtrip_preserves_availability_and_evidence(world, focused):
    root, repo, service, binding, _ = world
    document, clause, example, manifest = setup_source(world)
    gateway = Gateway()
    started = []

    @contextmanager
    def context(model):
        started.append(model.id)
        yield gateway

    run_dir = root / "partial"
    result = run_partial_cascade(
        manifest=manifest,
        examples=(example,),
        resources=RESOURCES,
        output_directory=run_dir,
        execute=True,
        gateway_context=context,
        completion_profile=CompletionProfile(required_attributes=("primary_function",))
        if focused
        else None,
    )
    assert result["metrics"]["completed_clause_count"] == 1
    assert gateway.calls == (0 if focused else 4)
    assert len(started) == gateway.calls
    mixed = MixedConsensusReport.model_validate_json(
        (run_dir / "mixed-consensus-report.json").read_bytes()
    )
    run_mixed_applicability(
        report=mixed,
        examples=(example,),
        manifest=manifest,
        root=run_dir,
        resources=RESOURCES,
        gateway_context=context,
    )
    assert gateway.calls == (0 if focused else 4)
    archive = archive_partial_cascade(
        root=run_dir, archive_directory=root / "archives", resources=RESOURCES
    )
    batch = load_qualification_knowledge(archive)
    assert batch.schema_version == "1.1"
    assert batch.candidates[0].source_requirements
    adopter = KnowledgeAdoptionService(documents=repo)
    adopter.apply(batch, write=True)
    original = repo.load(document.key)
    original_clause = next(c for c in original.clauses if c.id == clause.id)
    before = project_clause_enrichments(original_clause)
    service.export(write=True)
    public = binding.enrichments_path.read_bytes()
    assert b"enrichments.semantic.applicability_functions" not in public
    assert b"Synthetic term." not in public
    if focused:
        assert b"enrichments.semantic.statement_functions" not in public
    assert not service.export(write=True).written_targets
    repo.delete(document.key)
    service.import_(write=True, strict_evidence=True)
    restored = repo.load(document.key)
    restored_clause = next(c for c in restored.clauses if c.id == clause.id)
    assert restored_clause.enrichments == original_clause.enrichments
    after = project_clause_enrichments(restored_clause)
    differing = [
        (a.path, a.model_dump(mode="json"), b.model_dump(mode="json"))
        for a, b in zip(before.attributes, after.attributes, strict=True)
        if a != b
    ]
    # The current snapshot deliberately publishes presence only for roles.
    # Unpublished private attributes are not reconstructed from a companion.
    assert {item[0] for item in differing}.issubset({"enrichments.semantic.role_relations"})
    assert not service.export(write=True).written_targets
    assert binding.enrichments_path.read_bytes() == public


@pytest.mark.parametrize("change", ["type", "authority"])
def test_adoption_refuses_changed_structural_authority_before_any_document_write(world, change):
    root, repo, _, _, _ = world
    document, clause, example, manifest = setup_source(world)
    directory = root / "partial"
    run_partial_cascade(
        manifest=manifest,
        examples=(example,),
        resources=RESOURCES,
        output_directory=directory,
        execute=True,
        completion_profile=CompletionProfile(required_attributes=("primary_function",)),
    )
    archive = archive_partial_cascade(
        root=directory, archive_directory=root / "archives", resources=RESOURCES
    )
    batch = load_qualification_knowledge(archive)
    changed = (
        clause.model_copy(update={"clause_type": ClauseType.OBJECTIVE})
        if change == "type"
        else clause.confirm_authoritative("clause_type", authority="different-review")
    )
    new_doc = document.model_copy(
        update={"clauses": tuple(changed if c.id == clause.id else c for c in document.clauses)}
    )
    repo.save(new_doc)
    with pytest.raises(ValueError, match="taxonomy source/authority changed"):
        KnowledgeAdoptionService(documents=repo).apply(batch, write=True)
    assert repo.load(document.key) == new_doc
